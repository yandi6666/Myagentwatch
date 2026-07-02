"""Smoke tests — core flow: heartbeat → state machine → pricing → agent message."""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_db_init_and_migrations():
    from myagentwatch.db import DB_PATH, init_db, database, _current_schema_version

    init_db()
    with database() as conn:
        v = _current_schema_version(conn)
        assert v >= 1, f"Schema version {v} < 1"
        cols = [r[1] for r in conn.execute("PRAGMA table_info(agents)")]
        for n in ["last_heartbeat_at", "status_since"]:
            assert n in cols, f"Missing column: {n}"

        chat_cols = [r[1] for r in conn.execute("PRAGMA table_info(chat_messages)")]
        for n in [
            "is_agent_initiated", "task_context", "share_type",
            "root_id", "metadata_json", "priority", "edited_at", "deleted_at",
        ]:
            assert n in chat_cols, f"Missing chat column: {n}"

        inbox_cols = [r[1] for r in conn.execute("PRAGMA table_info(inbox)")]
        for n in [
            "source_conversation_id", "source_message_id",
            "delivery_type", "source_title", "metadata_json",
        ]:
            assert n in inbox_cols, f"Missing inbox column: {n}"

        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for n in [
            "chat_attachments", "chat_conversation_state",
            "chat_conversation_members", "chat_message_mentions",
        ]:
            assert n in tables, f"Missing table: {n}"

        member_cols = [r[1] for r in conn.execute("PRAGMA table_info(chat_conversation_members)")]
        for n in ["participant_type", "participant_id", "role", "muted", "last_seen_message_id", "mention_count"]:
            assert n in member_cols, f"Missing chat member column: {n}"

        mention_cols = [r[1] for r in conn.execute("PRAGMA table_info(chat_message_mentions)")]
        for n in ["message_id", "conversation_id", "participant_id", "mention_type", "is_read"]:
            assert n in mention_cols, f"Missing chat mention column: {n}"

        user_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
        for n in ["role", "permissions_json", "permission_limits_json"]:
            assert n in user_cols, f"Missing users column: {n}"

        agent_cols = [r[1] for r in conn.execute("PRAGMA table_info(agents)")]
        for n in ["role", "permissions_json"]:
            assert n in agent_cols, f"Missing agents column: {n}"

        assert "agent_tasks" in tables, "Missing table: agent_tasks"
        task_cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_tasks)")]
        for n in [
            "agent_id", "agent_name", "agent_role", "requester_role",
            "task_type", "status", "source_conversation_id",
            "source_message_id", "required_capabilities_json",
            "allow_autostart", "lease_expires_at", "attempt_count",
            "max_attempts", "last_error", "approval_status",
            "approval_required", "approved_by", "approved_at",
            "rejected_by", "rejected_at", "rejected_reason",
        ]:
            assert n in task_cols, f"Missing agent_tasks column: {n}"

        assert "agent_task_events" in tables, "Missing table: agent_task_events"
        event_cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_task_events)")]
        for n in ["task_id", "event_type", "actor_id", "message", "data_json", "created_at"]:
            assert n in event_cols, f"Missing agent_task_events column: {n}"


def test_pricing_load_and_calculate():
    from myagentwatch.db import database
    from myagentwatch.pricing import load_pricing, calculate_cost, SEED_PRICING

    assert len(SEED_PRICING) >= 30, f"Only {len(SEED_PRICING)} seed entries"

    with database() as conn:
        table = load_pricing(conn)
        assert len(table) >= 30, f"Only {len(table)} models loaded"

        c = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000, table=table)
        assert abs(c - 18.0) < 0.1, f"Sonnet cost {c} != 18.0"

        c2 = calculate_cost("deepseek-chat", 1_000_000, 1_000_000, table=table)
        assert abs(c2 - 1.37) < 0.1, f"DeepSeek cost {c2} != 1.37"

        c3 = calculate_cost("unknown-model", 500_000, 300_000, table=table)
        assert c3 > 0, "Fallback cost must be > 0"


def test_heartbeat_and_state_machine():
    from myagentwatch.db import database

    now_ms = int(time.time() * 1000)
    test_id = f"test:smoke:claude-sonnet-4-6"
    test_name = "SmokeAgent"

    with database() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO agents (id, name, agent_type, model_id, status, "
            "last_heartbeat_at, last_seen_time, created_at, updated_at) "
            "VALUES (?, ?, 'claude_code', 'claude-sonnet-4-6', 'idle', ?, ?, ?, ?)",
            (test_id, test_name, now_ms, now_ms, now_ms, now_ms),
        )
        conn.commit()

        agent = conn.execute("SELECT * FROM agents WHERE id = ?", (test_id,)).fetchone()
        assert agent is not None, "Agent not inserted"
        assert agent["status"] == "idle"
        assert agent["last_heartbeat_at"] > 0

    # Simulate heartbeat via direct DB update (mimics flush_heartbeats)
    with database() as conn:
        conn.execute(
            "UPDATE agents SET last_heartbeat_at = ?, updated_at = ? WHERE id = ?",
            (now_ms + 60000, now_ms + 60000, test_id),
        )
        conn.commit()

        agent = conn.execute("SELECT * FROM agents WHERE id = ?", (test_id,)).fetchone()
        assert agent["last_heartbeat_at"] > now_ms, "Heartbeat not updated"

    # Cleanup
    with database() as conn:
        conn.execute("DELETE FROM agents WHERE id = ?", (test_id,))
        conn.commit()


def test_agent_message_persistence():
    from myagentwatch.db import database

    now_ms = int(time.time() * 1000)
    with database() as conn:
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, sender_type, sender_id, "
            "sender_name, content, msg_type, is_agent_initiated, task_context, "
            "share_type, timestamp) VALUES (1, 'agent', 'test:agent', 'TestBot', "
            "'Task completed', 'task_result', 1, '数据清洗完成', 'result', ?)",
            (now_ms,),
        )
        conn.commit()

        msg = conn.execute(
            "SELECT * FROM chat_messages WHERE timestamp = ?", (now_ms,)
        ).fetchone()
        assert msg is not None, "Message not inserted"
        assert msg["is_agent_initiated"] == 1
        assert msg["task_context"] == "数据清洗完成"
        assert msg["share_type"] == "result"

        conn.execute("DELETE FROM chat_messages WHERE timestamp = ?", (now_ms,))
        conn.commit()


def test_chat_v2_thread_attachment_model():
    from myagentwatch.db import database
    from myagentwatch.queries import insert_chat_message, query_chat_thread

    now_ms = int(time.time() * 1000)
    with database() as conn:
        conn.execute(
            "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
            ("smoke-chat-v2", now_ms),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        root = insert_chat_message(
            conn, conv_id, "human", "tester", "Tester", "root message", "text", None, now_ms,
            attachments=[{"type": "link", "url": "https://example.test", "title": "example"}],
            metadata={"source": "smoke"},
            priority="high",
        )
        reply = insert_chat_message(
            conn, conv_id, "agent", "agent:test", "Agent", "reply message", "text",
            root["id"], now_ms + 1,
        )
        thread = query_chat_thread(conn, reply["id"])
        assert thread is not None
        assert thread["thread_id"] == root["id"]
        assert thread["root"]["attachments"][0]["type"] == "link"
        assert thread["replies"][0]["reply_to"] == root["id"]
        assert thread["replies"][0]["root_id"] == root["id"]

        ids = (root["id"], reply["id"])
        conn.execute("DELETE FROM chat_attachments WHERE message_id IN (?, ?)", ids)
        conn.execute("DELETE FROM chat_messages WHERE id IN (?, ?)", ids)
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.commit()


def test_inbox_v2_structured_fields():
    from myagentwatch.db import database
    from routes.api import _create_inbox_item

    item_id = _create_inbox_item(
        recipient_type="agent",
        recipient_id="agent:test",
        item_type="chat_message",
        severity="info",
        title="mention: Tester",
        body="hello",
        link="chat:123:msg:456",
        source_agent="tester",
        source_conversation_id=123,
        source_message_id=456,
        delivery_type="mention",
        source_title="smoke",
        metadata={"sender_name": "Tester"},
    )
    with database() as conn:
        row = conn.execute("SELECT * FROM inbox WHERE id = ?", (item_id,)).fetchone()
        assert row is not None
        assert row["source_conversation_id"] == 123
        assert row["source_message_id"] == 456
        assert row["delivery_type"] == "mention"
        assert row["source_title"] == "smoke"
        assert "Tester" in row["metadata_json"]
        conn.execute("DELETE FROM inbox WHERE id = ?", (item_id,))
        conn.commit()


def test_agent_tasks_v3_trigger_and_permissions():
    from myagentwatch.agent_tasks import create_agent_task
    from myagentwatch.db import database
    from myagentwatch.queries import insert_chat_message
    from routes.chat_api import _deliver_agent_inbox

    now_ms = int(time.time() * 1000)
    agent_id = f"agent:v3smoke:{now_ms}"
    agent_name = f"v3smoke{now_ms}"
    member_id = f"user-v3smoke-{now_ms}"

    with database() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, display_name, status, role, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', 'agent-worker', ?, ?)",
            (agent_id, agent_name, agent_name, now_ms, now_ms),
        )
        conn.execute(
            "INSERT INTO users (id, name, type, role, created_at) VALUES (?, ?, 'human', 'user-member', ?)",
            (member_id, "Member Smoke", now_ms),
        )
        conn.execute(
            "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
            ("v3-smoke", now_ms),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        plain = insert_chat_message(
            conn, conv_id, "human", "", "天宇", "今天先整理一下思路", "text", None, now_ms
        )
        before = conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0]
        _deliver_agent_inbox(conv_id, plain)
        after = conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0]
        assert after == before, "Plain group chat must not create agent task"

        mention = insert_chat_message(
            conn, conv_id, "human", "", "天宇", f"@{agent_name} 看一下这个错误", "text", None, now_ms + 1
        )
        _deliver_agent_inbox(conv_id, mention)
        task = conn.execute(
            "SELECT * FROM agent_tasks WHERE agent_id=? AND source_message_id=?",
            (agent_id, mention["id"]),
        ).fetchone()
        assert task is not None, "Mention should create reply task"
        assert task["task_type"] == "reply"
        assert task["source_conversation_id"] == conv_id
        assert task["allow_autostart"] == 1

        denied, reason = create_agent_task(
            conn,
            agent_id=agent_id,
            task_type="code_change",
            title="member code denied",
            body="change code",
            requester_id=member_id,
            requester_name="Member Smoke",
        )
        assert denied is None
        assert reason and "can_request_code_change" in reason

        conn.execute("DELETE FROM agent_tasks WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM inbox WHERE recipient_id = ?", (agent_id,))
        conn.execute("DELETE FROM chat_conversation_state WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (member_id,))
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()


def test_agent_tasks_v3_claim_complete_writes_chat():
    from myagentwatch.agent_tasks import claim_agent_task, complete_agent_task, create_agent_task, start_agent_task
    from myagentwatch.db import database

    now_ms = int(time.time() * 1000)
    agent_id = f"agent:v3claim:{now_ms}"

    with database() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, display_name, status, role, created_at, updated_at) "
            "VALUES (?, 'ClaimBot', 'ClaimBot', 'active', 'agent-worker', ?, ?)",
            (agent_id, now_ms, now_ms),
        )
        conn.execute(
            "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
            ("v3-claim", now_ms),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, sender_type, sender_id, sender_name, content, timestamp) "
            "VALUES (?, 'human', '', '天宇', 'root', ?)",
            (conv_id, now_ms),
        )
        source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        task, reason = create_agent_task(
            conn,
            agent_id=agent_id,
            task_type="reply",
            title="claim smoke",
            body="please reply",
            requester_id="tianyu",
            requester_name="天宇",
            source_conversation_id=conv_id,
            source_message_id=source_id,
            source_title="v3-claim",
        )
        assert reason is None
        assert task and task["allow_autostart"]

        claimed = claim_agent_task(
            conn,
            agent_id=agent_id,
            claimed_by="smoke-daemon",
            allowed_task_types=["reply"],
        )
        assert claimed is not None
        assert claimed["status"] == "claimed"
        running = start_agent_task(conn, claimed["id"])
        assert running["status"] == "running"
        done = complete_agent_task(conn, claimed["id"], "claim complete reply")
        assert done["status"] == "completed"

        reply = conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id=? AND sender_id=? AND content=?",
            (conv_id, agent_id, "claim complete reply"),
        ).fetchone()
        assert reply is not None
        assert reply["reply_to"] == source_id

        conn.execute("DELETE FROM agent_tasks WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()


def test_agent_tasks_v5_lease_events_recover():
    from myagentwatch.agent_tasks import (
        claim_agent_task,
        create_agent_task,
        fail_agent_task,
        get_agent_task,
        list_agent_task_events,
        recover_expired_agent_tasks,
        start_agent_task,
    )
    from myagentwatch.db import database
    from myagentwatch.queries import query_chat_message_context

    now_ms = int(time.time() * 1000)
    agent_id = f"agent:v5lease:{now_ms}"

    with database() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, display_name, status, role, created_at, updated_at) "
            "VALUES (?, 'LeaseBot', 'LeaseBot', 'active', 'agent-worker', ?, ?)",
            (agent_id, now_ms, now_ms),
        )
        conn.execute(
            "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
            ("v5-lease", now_ms),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, sender_type, sender_id, sender_name, content, timestamp) "
            "VALUES (?, 'human', '', '天宇', 'lease root', ?)",
            (conv_id, now_ms),
        )
        source_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        task, reason = create_agent_task(
            conn,
            agent_id=agent_id,
            task_type="reply",
            title="lease smoke",
            body="please reply",
            requester_id="tianyu",
            requester_name="天宇",
            source_conversation_id=conv_id,
            source_message_id=source_id,
            source_title="v5-lease",
        )
        assert reason is None
        assert task is not None
        assert any(e["event_type"] == "created" for e in list_agent_task_events(conn, task["id"]))

        claimed = claim_agent_task(
            conn,
            agent_id=agent_id,
            claimed_by="smoke-daemon",
            allowed_task_types=["reply"],
            lease_seconds=1,
        )
        assert claimed is not None
        assert claimed["status"] == "claimed"
        assert claimed["attempt_count"] == 1
        assert claimed["lease_expires_at"]

        recovered = recover_expired_agent_tasks(conn, now=int(claimed["lease_expires_at"]) + 1)
        assert recovered == 1
        queued = get_agent_task(conn, task["id"])
        assert queued["status"] == "queued"
        assert queued["last_error"] == "lease_expired_requeued"

        claimed_again = claim_agent_task(
            conn,
            agent_id=agent_id,
            claimed_by="smoke-daemon",
            allowed_task_types=["reply"],
        )
        assert claimed_again["attempt_count"] == 2
        running = start_agent_task(conn, claimed_again["id"], actor_id="smoke-daemon")
        assert running["status"] == "running"
        failed = fail_agent_task(conn, claimed_again["id"], "v5 smoke failure")
        assert failed["status"] == "failed"
        assert not failed["lease_expires_at"]
        assert failed["last_error"] == "v5 smoke failure"

        events = list_agent_task_events(conn, task["id"])
        event_types = [e["event_type"] for e in events]
        for expected in ["created", "claimed", "requeued", "started", "failed"]:
            assert expected in event_types, f"Missing task event: {expected}"

        context = query_chat_message_context(conn, source_id)
        assert context and context["tasks"]
        assert context["tasks"][0]["events"], "Context should include task event timeline"

        conn.execute("DELETE FROM agent_task_events WHERE task_id = ?", (task["id"],))
        conn.execute("DELETE FROM agent_tasks WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()


def test_chat_v4_channel_mentions_context():
    from myagentwatch.db import database
    from myagentwatch.queries import (
        insert_chat_message,
        mark_conversation_read,
        query_chat_conversations,
        query_chat_mentions,
        query_chat_message_context,
    )
    from routes.chat_api import _agent_recipients_for_message, _apply_chat_v4_delivery, _deliver_agent_inbox

    now_ms = int(time.time() * 1000)
    agent_id = f"agent:v4channel:{now_ms}"
    agent_name = f"v4channel{now_ms}"

    with database() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, display_name, status, role, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', 'agent-worker', ?, ?)",
            (agent_id, agent_name, agent_name, now_ms, now_ms),
        )
        conn.execute(
            "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
            ("v4-channel", now_ms),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        before_tasks = conn.execute("SELECT COUNT(*) FROM agent_tasks WHERE agent_id=?", (agent_id,)).fetchone()[0]
        plain = insert_chat_message(
            conn, conv_id, "human", "", "天宇", "今天先整理一下思路", "text", None, now_ms
        )
        _apply_chat_v4_delivery(conv_id, plain, [])
        _deliver_agent_inbox(conv_id, plain, recipients=[])
        after_tasks = conn.execute("SELECT COUNT(*) FROM agent_tasks WHERE agent_id=?", (agent_id,)).fetchone()[0]
        assert after_tasks == before_tasks, "Plain group chat must not create v4 task"

        convs = query_chat_conversations(conn, participant_type="agent", participant_id=agent_id)
        target_conv = next((c for c in convs if c["id"] == conv_id), None)
        assert target_conv is not None, "Agent should see group conversation as member"
        assert target_conv["unread_count"] >= 1
        assert target_conv["mention_count"] == 0

        mention = insert_chat_message(
            conn, conv_id, "human", "", "天宇", f"@{agent_name} 看一下这个错误", "text", None, now_ms + 1
        )
        recipients = _agent_recipients_for_message(conv_id, mention["content"], mention["sender_type"])
        assert any(r["id"] == agent_id and r["reason"] == "mention" for r in recipients)
        _apply_chat_v4_delivery(conv_id, mention, recipients)
        _deliver_agent_inbox(conv_id, mention, recipients=recipients)

        mentions = query_chat_mentions(conn, participant_type="agent", participant_id=agent_id, unread_only=True)
        assert any(int(m["message_id"]) == int(mention["id"]) for m in mentions), "Mention center should include @Agent"

        context = query_chat_message_context(conn, mention["id"])
        assert context is not None
        assert context["tasks"], "Message context should include associated agent task"
        assert context["tasks"][0]["source_message_id"] == mention["id"]

        mark_conversation_read(conn, conv_id, "agent", agent_id)
        convs = query_chat_conversations(conn, participant_type="agent", participant_id=agent_id)
        target_conv = next((c for c in convs if c["id"] == conv_id), None)
        assert target_conv["unread_count"] == 0
        assert target_conv["mention_count"] == 0
        mentions_after = query_chat_mentions(conn, participant_type="agent", participant_id=agent_id, unread_only=True)
        assert not any(int(m["message_id"]) == int(mention["id"]) for m in mentions_after)

        conn.execute("DELETE FROM agent_tasks WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM inbox WHERE recipient_id = ?", (agent_id,))
        conn.execute("DELETE FROM chat_message_mentions WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversation_members WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversation_state WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()


def test_agent_tasks_v6_approval_retry_claim_rules():
    from myagentwatch.agent_tasks import (
        approve_agent_task,
        claim_agent_task,
        create_agent_task,
        get_agent_task,
        list_agent_task_events,
        reject_agent_task,
        retry_agent_task,
    )
    from myagentwatch.db import database

    now_ms = int(time.time() * 1000)
    agent_id = f"agent:v6approval:{now_ms}"

    with database() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, display_name, status, role, created_at, updated_at) "
            "VALUES (?, 'ApprovalBot', 'ApprovalBot', 'active', 'agent-worker', ?, ?)",
            (agent_id, now_ms, now_ms),
        )
        conn.execute(
            "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
            ("v6-approval", now_ms),
        )
        conn.commit()
        conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        source_ids = []
        for content in ("approval root 1", "approval root 2"):
            conn.execute(
                "INSERT INTO chat_messages (conversation_id, sender_type, sender_id, sender_name, content, timestamp) "
                "VALUES (?, 'human', '', '天宇', ?, ?)",
                (conv_id, content, now_ms),
            )
            source_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        task, reason = create_agent_task(
            conn,
            agent_id=agent_id,
            task_type="reply",
            title="v6 approval claim",
            body="please reply",
            requester_id="tianyu",
            requester_name="天宇",
            source_conversation_id=conv_id,
            source_message_id=source_ids[0],
            source_title="v6-approval",
        )
        assert reason is None
        assert task is not None
        assert task["approval_status"] == "not_required"
        assert task["approval_required"] is False

        conn.execute(
            "UPDATE agent_tasks SET approval_required=1, approval_status='pending' WHERE id=?",
            (task["id"],),
        )
        conn.commit()
        pending = get_agent_task(conn, task["id"])
        assert pending["approval_status"] == "pending"
        blocked = claim_agent_task(
            conn,
            agent_id=agent_id,
            claimed_by="smoke-daemon",
            task_id=task["id"],
            allowed_task_types=["reply"],
        )
        assert blocked is None, "Pending task must not be claimable"

        approved = approve_agent_task(conn, task["id"], actor_id="tianyu", actor_name="天宇")
        assert approved["approval_status"] == "approved"
        claimed = claim_agent_task(
            conn,
            agent_id=agent_id,
            claimed_by="smoke-daemon",
            task_id=task["id"],
            allowed_task_types=["reply"],
        )
        assert claimed is not None
        assert claimed["status"] == "claimed"

        rejected_task, reason = create_agent_task(
            conn,
            agent_id=agent_id,
            task_type="reply",
            title="v6 rejected retry",
            body="please reply later",
            requester_id="tianyu",
            requester_name="天宇",
            source_conversation_id=conv_id,
            source_message_id=source_ids[1],
            source_title="v6-approval",
        )
        assert reason is None
        conn.execute(
            "UPDATE agent_tasks SET approval_required=1, approval_status='pending' WHERE id=?",
            (rejected_task["id"],),
        )
        conn.commit()

        rejected = reject_agent_task(conn, rejected_task["id"], actor_id="tianyu", reason="not safe yet")
        assert rejected["approval_status"] == "rejected"
        blocked_rejected = claim_agent_task(
            conn,
            agent_id=agent_id,
            claimed_by="smoke-daemon",
            task_id=rejected_task["id"],
            allowed_task_types=["reply"],
        )
        assert blocked_rejected is None, "Rejected task must not be claimable"

        retried = retry_agent_task(conn, rejected_task["id"], actor_id="tianyu", actor_name="天宇")
        assert retried["status"] == "queued"
        assert retried["approval_status"] == "pending"

        events = list_agent_task_events(conn, rejected_task["id"])
        event_types = [e["event_type"] for e in events]
        for expected in ["created", "rejected", "retried"]:
            assert expected in event_types, f"Missing v6 task event: {expected}"

        conn.execute("DELETE FROM agent_task_events WHERE task_id IN (?, ?)", (task["id"], rejected_task["id"]))
        conn.execute("DELETE FROM agent_tasks WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()


def test_friend_requests():
    from myagentwatch.db import database

    now_ms = int(time.time() * 1000)
    with database() as conn:
        conn.execute(
            "INSERT INTO friend_requests (from_agent_id, to_agent_id, "
            "from_agent_name, message, created_at) VALUES (?, ?, ?, ?, ?)",
            ("agent-a", "agent-b", "Alpha", "let us collaborate", now_ms),
        )
        conn.commit()

        req = conn.execute("SELECT * FROM friend_requests WHERE created_at = ?", (now_ms,)).fetchone()
        assert req is not None, "Friend request not inserted"
        assert req["status"] == "pending"

        conn.execute(
            "UPDATE friend_requests SET status = 'accepted', resolved_at = ? WHERE id = ?",
            (now_ms, req["id"]),
        )
        conn.commit()

        req2 = conn.execute("SELECT * FROM friend_requests WHERE id = ?", (req["id"],)).fetchone()
        assert req2["status"] == "accepted"

        conn.execute("DELETE FROM friend_requests WHERE id = ?", (req["id"],))
        conn.commit()


def test_pricing_crud():
    from myagentwatch.db import database

    now_ms = int(time.time() * 1000)
    with database() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pricing (provider_id, model_id, display_name, "
            "price_per_1m_input, price_per_1m_output, is_active, created_at) "
            "VALUES ('custom', 'test-model', 'Test Model', 0.5, 2.0, 1, ?)",
            (now_ms,),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM pricing WHERE model_id = 'test-model'"
        ).fetchone()
        assert row is not None, "Custom pricing not inserted"
        assert abs(row["price_per_1m_input"] - 0.5) < 0.01

        conn.execute("UPDATE pricing SET is_active = 0 WHERE model_id = 'test-model'")
        conn.commit()

        row2 = conn.execute(
            "SELECT * FROM pricing WHERE model_id = 'test-model' AND is_active = 1"
        ).fetchone()
        assert row2 is None, "Deactivated pricing still visible"

        conn.execute("DELETE FROM pricing WHERE model_id = 'test-model'")
        conn.commit()


if __name__ == "__main__":
    tests = [
        ("DB init & migrations", test_db_init_and_migrations),
        ("Pricing load & calculate", test_pricing_load_and_calculate),
        ("Heartbeat & state machine", test_heartbeat_and_state_machine),
        ("Agent message persistence", test_agent_message_persistence),
        ("Chat v2 thread/attachment", test_chat_v2_thread_attachment_model),
        ("Inbox v2 structured fields", test_inbox_v2_structured_fields),
        ("Agent tasks v3 trigger/permissions", test_agent_tasks_v3_trigger_and_permissions),
        ("Agent tasks v3 claim/complete", test_agent_tasks_v3_claim_complete_writes_chat),
        ("Agent tasks v5 lease/events", test_agent_tasks_v5_lease_events_recover),
        ("Chat v4 channel/mentions/context", test_chat_v4_channel_mentions_context),
        ("Agent tasks v6 approval/retry/claim", test_agent_tasks_v6_approval_retry_claim_rules),
        ("Friend requests", test_friend_requests),
        ("Pricing CRUD", test_pricing_crud),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK  {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL {name}: {e}")

    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
