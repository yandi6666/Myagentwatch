"""MyAgentWatch Chat API - REST endpoints for conversations/messages."""

import logging
import re
import threading
import time

from flask import jsonify, request
from myagentwatch.agent_tasks import create_agent_task, find_agent_by_name, infer_task_type_from_content
from myagentwatch.db import database
from myagentwatch.queries import (
    apply_chat_member_delivery,
    query_chat_contacts,
    query_chat_conversations,
    query_chat_message,
    query_chat_message_context,
    query_chat_messages,
    query_chat_mentions,
    query_chat_thread,
    query_chat_unread_total,
    query_or_create_conversation,
    insert_chat_message,
    mark_conversation_read,
)

logger = logging.getLogger("myagentwatch.chat")


def _emit_async(sio, event, data):
    """Emit WebSocket event in a background thread to avoid blocking HTTP response."""
    def _do():
        try:
            sio.emit(event, data)
        except Exception:
            pass
    threading.Thread(target=_do, daemon=True).start()


def _mention_tokens(agent: dict) -> set[str]:
    tokens = set()
    for key in ("id", "name", "display_name"):
        value = (agent.get(key) or "").strip()
        if value:
            tokens.add("@" + value.lower())
    return tokens


def _mention_words(content: str) -> set[str]:
    words = set()
    for raw in re.findall(r"@([^\s@,，。.!！?？;；]+)", content or ""):
        token = raw.strip().lower()
        if token:
            words.add(token)
    return words


def _agent_recipients_for_message(conv_id: int, content: str, sender_type: str) -> list[dict]:
    if sender_type == "agent":
        return []
    text = content.lower()
    recipients = {}
    task_type, explicit_target, task_body = infer_task_type_from_content(content)
    with database() as conn:
        conv = conn.execute(
            "SELECT type, agent_id, title FROM chat_conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        agents = conn.execute(
            "SELECT id, name, display_name FROM agents WHERE status != 'removed'"
        ).fetchall()
        command_agent = find_agent_by_name(conn, explicit_target) if explicit_target else None

    if conv and conv["type"] in ("private", "dm", "agent_dm") and conv["agent_id"]:
        recipients[conv["agent_id"]] = {
            "id": conv["agent_id"],
            "reason": "private",
            "task_type": "reply",
            "task_body": content,
        }

    if command_agent:
        recipients[command_agent["id"]] = {
            "id": command_agent["id"],
            "reason": "command",
            "task_type": task_type,
            "task_body": task_body or content,
        }

    for row in agents:
        agent = dict(row)
        if any(token in text for token in _mention_tokens(agent)):
            agent["reason"] = "mention"
            agent["task_type"] = "reply"
            agent["task_body"] = content
            recipients[agent["id"]] = agent
    return list(recipients.values())


def _structured_mentions_for_message(content: str, recipients: list[dict]) -> list[dict]:
    words = _mention_words(content)
    mentions = []
    if "all" in words:
        mentions.append({
            "participant_type": "agent",
            "participant_id": "*",
            "mention_token": "@all",
            "mention_type": "all",
        })
    for agent in recipients:
        if agent.get("reason") != "mention":
            continue
        mentions.append({
            "participant_type": "agent",
            "participant_id": agent["id"],
            "mention_token": "@" + (agent.get("name") or agent.get("display_name") or agent["id"]),
            "mention_type": "direct",
        })
    return mentions


def _apply_chat_v4_delivery(conv_id: int, msg: dict, recipients: list[dict] | None = None):
    recipients = recipients or _agent_recipients_for_message(
        conv_id,
        msg.get("content", ""),
        msg.get("sender_type", ""),
    )
    mentions = _structured_mentions_for_message(msg.get("content", ""), recipients)
    with database() as conn:
        apply_chat_member_delivery(conn, conv_id, msg, mentions=mentions)


def _conversation_info(conv_id: int) -> dict:
    with database() as conn:
        row = conn.execute(
            "SELECT id, type, title, agent_id FROM chat_conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
    if not row:
        return {"id": conv_id, "type": "group", "title": f"#{conv_id}"}
    return dict(row)


def _delivery_title(reason: str, sender: str) -> str:
    label = "\u79c1\u804a" if reason == "private" else "\u63d0\u53ca"
    return f"{label}: {sender}"


def _deliver_agent_inbox(conv_id: int, msg: dict, recipients: list[dict] | None = None):
    recipients = recipients or _agent_recipients_for_message(
        conv_id,
        msg.get("content", ""),
        msg.get("sender_type", ""),
    )
    if not recipients:
        return

    from routes.api import _create_inbox_item

    conv = _conversation_info(conv_id)
    sender = msg.get("sender_name") or "\u5929\u5b87"
    priority = (msg.get("priority") or "").lower()
    severity = "warning" if priority in ("high", "urgent") else "info"
    metadata = {
        "sender_id": msg.get("sender_id") or "",
        "sender_name": sender,
        "sender_type": msg.get("sender_type") or "",
        "conversation_type": conv.get("type") or "group",
        "message_type": msg.get("msg_type") or "text",
        "root_id": msg.get("root_id"),
        "attachments": msg.get("attachments") or [],
    }
    for agent in recipients:
        reason = agent.get("reason") or "mention"
        inbox_id = _create_inbox_item(
            recipient_type="agent",
            recipient_id=agent["id"],
            item_type="chat_message",
            severity=severity,
            title=_delivery_title(reason, sender),
            body=(msg.get("content") or "")[:240],
            link=f"chat:{conv_id}:msg:{msg.get('id')}",
            source_agent=msg.get("sender_id") or "",
            source_conversation_id=conv_id,
            source_message_id=msg.get("id"),
            delivery_type=reason,
            source_title=conv.get("title") or f"#{conv_id}",
            metadata=metadata,
        )
        task_type = agent.get("task_type") or "reply"
        task_body = agent.get("task_body") or msg.get("content") or ""
        with database() as conn:
            task, denied = create_agent_task(
                conn,
                agent_id=agent["id"],
                task_type=task_type,
                title=_delivery_title(reason, sender),
                body=task_body,
                requester_id=msg.get("sender_id") or "",
                requester_name=sender,
                requester_type="user" if msg.get("sender_type") != "agent" else "agent",
                source_conversation_id=conv_id,
                source_message_id=msg.get("id"),
                source_title=conv.get("title") or f"#{conv_id}",
                metadata={**metadata, "delivery_type": reason, "inbox_id": inbox_id},
            )
            if denied:
                logger.info(
                    "agent task denied agent=%s message=%s reason=%s",
                    agent["id"],
                    msg.get("id"),
                    denied,
                )


def register_chat_routes(app, socketio):
    """Register chat API routes."""

    @app.route("/api/chat/conversations")
    def api_chat_conversations():
        participant_type = request.args.get("participant_type")
        participant_id = request.args.get("participant_id")
        limit = min(request.args.get("limit", 50, type=int), 200)
        with database() as conn:
            convs = query_chat_conversations(
                conn,
                limit=limit,
                participant_type=participant_type,
                participant_id=participant_id,
            )
        return jsonify({"conversations": convs})

    @app.route("/api/chat/conversations", methods=["POST"])
    def api_chat_create_conversation():
        data = request.get_json(silent=True) or {}
        conv_type = data.get("type", "private")
        agent_id = data.get("agent_id")
        title = data.get("title", agent_id or "\u7fa4\u804a")
        now = int(time.time() * 1000)
        with database() as conn:
            conv = query_or_create_conversation(conn, conv_type, agent_id, title, now)
        return jsonify({"conversation": conv})

    @app.route("/api/chat/messages/<int:conv_id>")
    def api_chat_messages(conv_id):
        before = request.args.get("before", type=int)
        after_id = request.args.get("after_id", type=int)
        limit = min(request.args.get("limit", 100, type=int), 200)
        with database() as conn:
            msgs = query_chat_messages(conn, conv_id, limit=limit, before_id=before, after_id=after_id)
        return jsonify({"messages": msgs})

    @app.route("/api/chat/messages/<int:message_id>/thread")
    def api_chat_thread(message_id):
        limit = min(request.args.get("limit", 100, type=int), 200)
        with database() as conn:
            thread = query_chat_thread(conn, message_id, limit=limit)
        if not thread:
            return jsonify({"error": "message_not_found"}), 404
        return jsonify({"thread": thread})

    @app.route("/api/chat/messages/<int:message_id>/context")
    def api_chat_message_context(message_id):
        with database() as conn:
            context = query_chat_message_context(conn, message_id)
        if not context:
            return jsonify({"error": "message_not_found"}), 404
        return jsonify({"context": context})

    @app.route("/api/chat/mentions")
    def api_chat_mentions():
        participant_type = request.args.get("participant_type") or "agent"
        participant_id = request.args.get("participant_id") or ""
        unread_only = request.args.get("unread", "0") in ("1", "true", "yes")
        limit = min(request.args.get("limit", 50, type=int), 200)
        with database() as conn:
            mentions = query_chat_mentions(
                conn,
                participant_type=participant_type,
                participant_id=participant_id,
                unread_only=unread_only,
                limit=limit,
            )
        return jsonify({"mentions": mentions})

    @app.route("/api/chat/messages/<int:conv_id>", methods=["POST"])
    def api_chat_send_message(conv_id):
        data = request.get_json(silent=True) or {}
        content = (data.get("message") or data.get("content") or "").strip()
        if not content:
            return jsonify({"error": "empty message"}), 400

        sender_type = data.get("sender_type", "human")
        sender_id = data.get("sender_id", "")
        sender_name = data.get("sender_name", "\u5929\u5b87")
        msg_type = data.get("msg_type", "text")
        reply_to = data.get("reply_to")
        root_id = data.get("root_id")
        attachments = data.get("attachments") or []
        metadata = data.get("metadata") or {}
        priority = data.get("priority", "")
        now = int(time.time() * 1000)

        with database() as conn:
            msg = insert_chat_message(
                conn, conv_id, sender_type, sender_id, sender_name,
                content, msg_type, reply_to, now,
                root_id=root_id,
                attachments=attachments,
                metadata=metadata,
                priority=priority,
            )
        recipients = _agent_recipients_for_message(conv_id, msg.get("content", ""), msg.get("sender_type", ""))
        _apply_chat_v4_delivery(conv_id, msg, recipients)
        _deliver_agent_inbox(conv_id, msg, recipients=recipients)
        _emit_async(socketio, "chat_message", {
            "conversation_id": conv_id,
            "message": msg,
            "timestamp": now,
        })
        return jsonify({"message": msg})

    @app.route("/api/chat/broadcast", methods=["POST"])
    def api_chat_broadcast():
        data = request.get_json(silent=True) or {}
        content = (data.get("message") or data.get("content") or "").strip()
        if not content:
            return jsonify({"error": "empty message"}), 400

        sender_name = data.get("sender_name", "\u5929\u5b87")
        now = int(time.time() * 1000)
        with database() as conn:
            conv = conn.execute(
                "SELECT id FROM chat_conversations WHERE type='group' ORDER BY id LIMIT 1"
            ).fetchone()
            if not conv:
                conn.execute(
                    "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
                    ("\u7fa4\u804a\u5e7f\u64ad", now),
                )
                conn.commit()
                conv = conn.execute(
                    "SELECT id FROM chat_conversations WHERE type='group' ORDER BY id LIMIT 1"
                ).fetchone()

            msg = insert_chat_message(
                conn, conv["id"], "human", "", sender_name,
                content, "text", None, now,
                attachments=data.get("attachments") or [],
                metadata=data.get("metadata") or {},
                priority=data.get("priority", ""),
            )
        recipients = _agent_recipients_for_message(conv["id"], msg.get("content", ""), msg.get("sender_type", ""))
        _apply_chat_v4_delivery(conv["id"], msg, recipients)
        _deliver_agent_inbox(conv["id"], msg, recipients=recipients)
        _emit_async(socketio, "chat_message", {
            "conversation_id": conv["id"],
            "message": msg,
            "timestamp": now,
        })
        return jsonify({"message": msg})

    @app.route("/api/chat/contacts")
    def api_chat_contacts():
        with database() as conn:
            contacts = query_chat_contacts(conn)
        return jsonify({"contacts": contacts})

    @app.route("/api/chat/unread-count")
    def api_chat_unread_count():
        with database() as conn:
            total = query_chat_unread_total(conn)
        return jsonify({"unread_count": total})

    @app.route("/api/chat/read/<int:conv_id>", methods=["POST"])
    def api_chat_read(conv_id):
        data = request.get_json(silent=True) or {}
        participant_type = request.args.get("participant_type") or data.get("participant_type")
        participant_id = request.args.get("participant_id") or data.get("participant_id")
        with database() as conn:
            mark_conversation_read(conn, conv_id, participant_type, participant_id)
        return jsonify({"status": "ok"})

    @app.route("/api/chat/agent-message", methods=["POST"])
    def api_chat_agent_message():
        data = request.get_json(silent=True) or {}
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"error": "empty content"}), 400

        conv_id = data.get("conversation_id")
        agent_id = data.get("agent_id", "")
        agent_name = data.get("agent_name", "Agent")
        share_type = data.get("share_type", "none")
        task_context = data.get("task_context", "")
        now = int(time.time() * 1000)

        with database() as conn:
            if not conv_id:
                conv = conn.execute(
                    "SELECT id FROM chat_conversations WHERE type='group' ORDER BY id LIMIT 1"
                ).fetchone()
                if not conv:
                    conn.execute(
                        "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', ?, ?)",
                        ("Agent \u7fa4\u804a", now),
                    )
                    conn.commit()
                    conv = conn.execute(
                        "SELECT id FROM chat_conversations WHERE type='group' ORDER BY id LIMIT 1"
                    ).fetchone()
                conv_id = conv["id"]
            conv_id = int(conv_id)
            msg = insert_chat_message(
                conn, conv_id, "agent", agent_id, agent_name, content,
                "task_result" if share_type != "none" else "text",
                data.get("reply_to"), now,
                root_id=data.get("root_id"),
                attachments=data.get("attachments") or [],
                metadata=data.get("metadata") or {},
                priority=data.get("priority", ""),
                is_agent_initiated=1,
                task_context=task_context,
                share_type=share_type,
            )

        _apply_chat_v4_delivery(conv_id, msg)
        _emit_async(socketio, "chat_message", {
            "conversation_id": conv_id,
            "message": msg,
            "timestamp": now,
        })
        from routes.api import _create_inbox_item
        _create_inbox_item(
            recipient_id="\u5929\u5b87",
            title=f"Agent message: {agent_name}",
            body=content[:120],
            item_type="agent_message",
            severity="info",
            link=f"chat:{conv_id}:msg:{msg.get('id')}",
            source_agent=agent_id,
            source_conversation_id=conv_id,
            source_message_id=msg.get("id"),
            delivery_type="agent_message",
            source_title=_conversation_info(conv_id).get("title") or f"#{conv_id}",
            metadata={"sender_id": agent_id, "sender_name": agent_name, "sender_type": "agent"},
        )
        return jsonify({"message": msg})

    @app.route("/api/chat/friend-request", methods=["POST"])
    def api_chat_friend_request():
        data = request.get_json(silent=True) or {}
        from_id = data.get("from_agent_id", "")
        to_id = data.get("to_agent_id", "")
        from_name = data.get("from_agent_name", "Agent")
        message = data.get("message", "")
        if not from_id:
            return jsonify({"error": "from_agent_id required"}), 400
        now = int(time.time() * 1000)
        with database() as conn:
            conn.execute(
                "INSERT INTO friend_requests (from_agent_id, to_agent_id, "
                "from_agent_name, message, created_at) VALUES (?, ?, ?, ?, ?)",
                (from_id, to_id, from_name, message, now),
            )
            conn.commit()
            req = conn.execute(
                "SELECT * FROM friend_requests WHERE id = last_insert_rowid()"
            ).fetchone()
        _emit_async(socketio, "friend_request", dict(req) if req else {})
        from routes.api import _create_inbox_item
        _create_inbox_item(
            recipient_id="\u5929\u5b87", title=f"Friend request: {from_name}",
            body=message[:120] if message else f"Agent {from_name} requested contact",
            item_type="friend_request", severity="info",
            source_agent=from_id,
            delivery_type="friend_request",
            metadata={"from_agent_id": from_id, "to_agent_id": to_id},
        )
        return jsonify({"request": dict(req) if req else {}})

    @app.route("/api/chat/friend-requests")
    def api_chat_friend_requests():
        with database() as conn:
            rows = conn.execute(
                "SELECT * FROM friend_requests WHERE status = 'pending' "
                "ORDER BY created_at DESC"
            ).fetchall()
        return jsonify({"requests": [dict(r) for r in rows]})

    @app.route("/api/chat/friend-request/<int:req_id>/accept", methods=["POST"])
    def api_chat_friend_accept(req_id):
        now = int(time.time() * 1000)
        with database() as conn:
            conn.execute(
                "UPDATE friend_requests SET status = 'accepted', "
                "resolved_at = ? WHERE id = ?", (now, req_id),
            )
            conn.commit()
        return jsonify({"status": "ok"})

    @app.route("/api/chat/friend-request/<int:req_id>/reject", methods=["POST"])
    def api_chat_friend_reject(req_id):
        now = int(time.time() * 1000)
        with database() as conn:
            conn.execute(
                "UPDATE friend_requests SET status = 'rejected', "
                "resolved_at = ? WHERE id = ?", (now, req_id),
            )
            conn.commit()
        return jsonify({"status": "ok"})

    @app.route("/api/chat/share-task/<int:conv_id>", methods=["POST"])
    def api_chat_share_task(conv_id):
        data = request.get_json(silent=True) or {}
        title = data.get("task_title", "Task completed")
        summary = data.get("result_summary", "")
        content = f"[{title}]\n{summary}"
        agent_id = data.get("agent_id", "")
        agent_name = data.get("agent_name", "Agent")
        now = int(time.time() * 1000)
        with database() as conn:
            msg = insert_chat_message(
                conn, conv_id, "agent", agent_id, agent_name, content,
                "task_result", data.get("reply_to"), now,
                root_id=data.get("root_id"),
                attachments=data.get("attachments") or [],
                metadata=data.get("metadata") or {"task_title": title},
                priority=data.get("priority", ""),
                is_agent_initiated=1,
                task_context=title,
                share_type="result",
            )
        _apply_chat_v4_delivery(conv_id, msg)
        _emit_async(socketio, "chat_message", {
            "conversation_id": conv_id,
            "message": msg,
            "timestamp": now,
        })
        return jsonify({"message": msg})
