"""Shared SQL query helpers used by routes and WebSocket push."""

import json
import time


def today_start_ms() -> int:
    return int(time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")) * 1000)


def query_overview_cards(conn) -> dict:
    today = today_start_ms()

    active = conn.execute(
        "SELECT COUNT(*) as cnt FROM agents WHERE status = 'active'"
    ).fetchone()["cnt"]
    tokens = conn.execute(
        "SELECT COALESCE(SUM(tokens_input), 0) as inp, "
        "COALESCE(SUM(tokens_output), 0) as outp, "
        "COALESCE(SUM(tokens_reasoning), 0) as reas "
        "FROM token_records WHERE timestamp >= ?",
        (today,),
    ).fetchone()
    cost = conn.execute(
        "SELECT COALESCE(SUM(cost), 0) as total FROM token_records WHERE timestamp >= ?",
        (today,),
    ).fetchone()["total"]
    failed = conn.execute(
        "SELECT COUNT(*) as cnt FROM tool_calls "
        "WHERE status IN ('error','failed') AND timestamp >= ?",
        (today,),
    ).fetchone()["cnt"]
    total_calls = conn.execute(
        "SELECT COUNT(*) as cnt FROM tool_calls WHERE timestamp >= ?", (today,)
    ).fetchone()["cnt"]
    success_rate = 0
    if total_calls > 0:
        success_rate = round((1 - failed / total_calls) * 100, 1)

    return {
        "active_agents": active,
        "total_tokens_today": (tokens["inp"] or 0)
        + (tokens["outp"] or 0)
        + (tokens["reas"] or 0),
        "tokens_input_today": tokens["inp"] or 0,
        "tokens_output_today": tokens["outp"] or 0,
        "success_rate": success_rate,
        "cost_today": round(cost or 0, 4),
    }


def query_agents_active(conn) -> list:
    rows = conn.execute(
        "SELECT id, name, display_name, group_name, agent_type, model_id, "
        "provider_id, status, last_seen_time "
        "FROM agents WHERE status != 'removed' ORDER BY group_name, name"
    ).fetchall()
    return [dict(r) for r in rows]


def query_chart_data(conn) -> dict:
    last_24h = int((time.time() - 86400) * 1000)

    tokens_by_agent = conn.execute(
        "SELECT a.display_name as name, a.id as agent_id, "
        "COALESCE(SUM(t.tokens_input), 0) as tokens_input, "
        "COALESCE(SUM(t.tokens_output), 0) as tokens_output, "
        "COALESCE(SUM(t.tokens_reasoning), 0) as tokens_reasoning "
        "FROM agents a LEFT JOIN token_records t ON t.agent_id = a.id "
        "WHERE a.status != 'removed' GROUP BY a.id"
    ).fetchall()

    # 最近 24 小时工具调用延迟
    last_24h = int((time.time() - 86400) * 1000)
    latency_rows = conn.execute(
        "SELECT agent_id, tool_name, duration_ms, timestamp "
        "FROM tool_calls WHERE timestamp >= ? "
        "ORDER BY timestamp ASC",
        (last_24h,),
    ).fetchall()

    # 填充 duration_ms（原数据很多为 0，用相邻记录时间差估算）
    for i in range(len(latency_rows) - 1, 0, -1):
        if (latency_rows[i]["duration_ms"] or 0) == 0:
            gap = latency_rows[i]["timestamp"] - latency_rows[i - 1]["timestamp"]
            if 0 < gap < 300000:
                latency_rows[i] = dict(latency_rows[i])
                latency_rows[i]["duration_ms"] = gap

    hourly = conn.execute(
        "SELECT (timestamp / 3600000) * 3600000 as hour_bucket, "
        "SUM(tokens_input) as inp, SUM(tokens_output) as outp, "
        "SUM(tokens_reasoning) as reas "
        "FROM token_records WHERE timestamp >= ? "
        "GROUP BY hour_bucket ORDER BY hour_bucket",
        (last_24h,),
    ).fetchall()

    return {
        "tokens_by_agent": [dict(r) for r in tokens_by_agent],
        "latency": [dict(r) for r in latency_rows],
        "hourly_tokens": [dict(r) for r in hourly],
    }


def query_topology(conn) -> dict:
    today = today_start_ms()

    nodes = conn.execute(
        "SELECT a.id, a.name, a.display_name, a.group_name, a.status, "
        "a.model_id, a.provider_id, a.last_seen_time, "
        "COALESCE(SUM(t.tokens_input + t.tokens_output + t.tokens_reasoning), 0) as tokens_total, "
        "COALESCE(SUM(t.cost), 0) as cost "
        "FROM agents a "
        "LEFT JOIN token_records t ON t.agent_id = a.id AND t.timestamp >= ? "
        "GROUP BY a.id "
        "ORDER BY a.group_name, a.name",
        (today,),
    ).fetchall()

    edges = conn.execute(
        "SELECT DISTINCT s1.agent_id as source_id, s2.agent_id as target_id, "
        "COUNT(*) as call_count "
        "FROM sessions s1 "
        "JOIN sessions s2 ON s2.parent_id = s1.id "
        "WHERE s1.agent_id != '' AND s2.agent_id != '' "
        "GROUP BY s1.agent_id, s2.agent_id"
    ).fetchall()

    node_list = []
    for n in nodes:
        d = dict(n)
        d["configured"] = bool(d.get("display_name"))
        d["group"] = d.pop("group_name", "") or "默认 (未配置)"
        node_list.append(d)

    edge_list = [
        {
            "source": e["source_id"],
            "target": e["target_id"],
            "call_count": e["call_count"],
            "parent_child": True,
        }
        for e in edges
    ]

    return {"nodes": node_list, "edges": edge_list}


def query_all_agents(conn) -> list:
    rows = conn.execute(
        "SELECT id, name, display_name, group_name, agent_type, model_id, "
        "provider_id, status, last_seen_time "
        "FROM agents WHERE status != 'removed' ORDER BY group_name, name"
    ).fetchall()
    return [dict(r) for r in rows]


def query_tree(conn) -> dict:
    """Build a tree of sessions and agents for deterministic tree layout.

    Returns:
        { "roots": [ { id, type, display_name, status, model_id, ...,
                       tokens_total, cost, latency_ms, children: [...] } ] }
    """
    sessions = conn.execute(
        "SELECT s.id, s.agent_id, s.title, s.parent_id, s.status, "
        "s.total_tokens_input, s.total_tokens_output, s.total_cost, "
        "s.time_created, s.time_updated "
        "FROM sessions s ORDER BY s.time_created"
    ).fetchall()

    agents = conn.execute(
        "SELECT id, name, display_name, group_name, agent_type, model_id, "
        "provider_id, status, last_seen_time "
        "FROM agents"
    ).fetchall()
    agent_by_id = {a["id"]: dict(a) for a in agents}

    # Latest tool call per agent for "current action"
    tools = conn.execute(
        "SELECT agent_id, tool_name, status, description, duration_ms, timestamp "
        "FROM tool_calls WHERE id IN ("
        "SELECT MAX(id) FROM tool_calls GROUP BY agent_id"
        ")"
    ).fetchall()
    tool_by_agent = {}
    for t in tools:
        tool_by_agent[t["agent_id"]] = dict(t)

    # Token sums per agent (last hour)
    one_hour_ago = int((time.time() - 3600) * 1000)
    token_rows = conn.execute(
        "SELECT agent_id, SUM(tokens_input) as inp, SUM(tokens_output) as outp, "
        "SUM(cache_read) as cr, SUM(cache_write) as cw, SUM(cost) as cost "
        "FROM token_records WHERE timestamp >= ? GROUP BY agent_id",
        (one_hour_ago,),
    ).fetchall()
    tokens_by_agent = {tr["agent_id"]: dict(tr) for tr in token_rows}

    # Build node lookup
    nodes_by_session = {}
    for s in sessions:
        sid = s["id"]
        agent = agent_by_id.get(s["agent_id"], {})
        tool = tool_by_agent.get(s["agent_id"], {})
        tokens = tokens_by_agent.get(s["agent_id"], {})

        # Resolve source from agent_id format "source:name:model"
        source = "unknown"
        if s["agent_id"] and ":" in s["agent_id"]:
            source = s["agent_id"].split(":")[0]

        nodes_by_session[sid] = {
            "id": s["agent_id"] or sid,
            "session_id": sid,
            "type": "agent",
            "display_name": agent.get("display_name") or agent.get("name", sid[:12]),
            "group_name": agent.get("group_name", ""),
            "agent_type": agent.get("agent_type", ""),
            "source": source,
            "model_id": agent.get("model_id", ""),
            "provider_id": agent.get("provider_id", ""),
            "status": agent.get("status", "offline"),
            "tokens_input": tokens.get("inp", 0) or 0,
            "tokens_output": tokens.get("outp", 0) or 0,
            "cache_read": tokens.get("cr", 0) or 0,
            "cache_write": tokens.get("cw", 0) or 0,
            "cost": round(tokens.get("cost", 0) or 0, 4),
            "tokens_total": (tokens.get("inp", 0) or 0) + (tokens.get("outp", 0) or 0),
            "latency_ms": tool.get("duration_ms", 0),
            "tool_name": tool.get("tool_name", ""),
            "tool_status": tool.get("status", ""),
            "current_action": tool.get("description", ""),
            "last_seen_time": agent.get("last_seen_time", 0),
            "title": s["title"] or "",
            "children": [],
        }

    # Build parent→child relationships
    child_ids = set()
    for s in sessions:
        if s["parent_id"] and s["parent_id"] in nodes_by_session and s["id"] in nodes_by_session:
            nodes_by_session[s["parent_id"]]["children"].append(nodes_by_session[s["id"]])
            child_ids.add(s["id"])

    # Roots: sessions that are NOT children of another session
    roots = []
    for s in sessions:
        sid = s["id"]
        if sid not in child_ids and sid in nodes_by_session:
            roots.append(nodes_by_session[sid])

    # If no tree structure, return flat list as roots
    if not roots:
        roots = [nodes_by_session[s["id"]] for s in sessions if s["id"] in nodes_by_session]

    return {"roots": roots}


def query_sessions(conn, limit=50) -> list:
    rows = conn.execute(
        "SELECT id, agent_id, title, slug, directory, status, parent_id, "
        "message_count, total_cost, time_created, time_updated "
        "FROM sessions ORDER BY time_updated DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── 对话日志查询 ──

def query_turns(
    conn,
    agent_id: str | None = None,
    phase: str | None = None,
    severity: str | None = None,
    search: str | None = None,
    trace_id: str | None = None,
    since: int | None = None,
    until: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """查询 conversation_turns，支持多维筛选和全文搜索。

    返回列表中的每个 dict 包含 turns 的基本字段 + 第一个 content block 预览。
    """
    where = ["1=1"]
    params: list = []

    if agent_id:
        where.append("t.agent_id = ?")
        params.append(agent_id)
    if phase:
        where.append("t.phase = ?")
        params.append(phase)
    if severity:
        where.append("t.severity = ?")
        params.append(severity)
    if trace_id:
        where.append("t.trace_id = ?")
        params.append(trace_id)
    if since:
        where.append("t.time_start >= ?")
        params.append(since)
    if until:
        where.append("t.time_start <= ?")
        params.append(until)

    if search:
        where.append(
            "EXISTS (SELECT 1 FROM turn_content tc "
            "JOIN turn_content_fts f ON f.rowid = tc.id "
            "WHERE tc.turn_id = t.id AND turn_content_fts MATCH ?)"
        )
        params.append(search)

    where_clause = " AND ".join(where)

    # 先查总数
    count_sql = f"SELECT COUNT(*) as cnt FROM conversation_turns t WHERE {where_clause}"
    total_row = conn.execute(count_sql, params).fetchone()
    total = total_row["cnt"] if total_row else 0

    # 再查分页数据
    sql = (
        f"SELECT t.*, "
        f"(SELECT tc.content FROM turn_content tc "
        f" WHERE tc.turn_id = t.id ORDER BY tc.id LIMIT 1) AS content_preview "
        f"FROM conversation_turns t "
        f"WHERE {where_clause} "
        f"ORDER BY t.time_start DESC "
        f"LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows], total


def query_turn_counts_by_agent(conn) -> list[dict]:
    """按 Agent 分组统计 Turn 数量，供左侧树使用。

    agent_id 是全局格式 {source_type}::{source_name}::{hash}::{role}::{name}::{model}，
    从中解析 display_name 和 group_name，不依赖 agents 表 JOIN。
    """
    rows = conn.execute(
        "SELECT agent_id, COUNT(*) as cnt "
        "FROM conversation_turns "
        "GROUP BY agent_id "
        "ORDER BY agent_id"
    ).fetchall()
    results = []
    for r in rows:
        parts = r["agent_id"].split("::")
        display = parts[4] if len(parts) >= 6 else r["agent_id"][:30]
        group = parts[0] if parts else ""
        results.append({
            "agent_id": r["agent_id"],
            "display_name": display,
            "group_name": group,
            "cnt": r["cnt"],
        })
    return results


def query_turn_detail(conn, turn_id: int) -> dict | None:
    """查询单个 Turn 的完整详情，包含所有 content blocks。"""
    turn = conn.execute(
        "SELECT * FROM conversation_turns WHERE id = ?", (turn_id,)
    ).fetchone()
    if not turn:
        return None

    blocks = conn.execute(
        "SELECT * FROM turn_content WHERE turn_id = ? ORDER BY id", (turn_id,)
    ).fetchall()

    handoff = None
    if turn["handoff_id"]:
        h = conn.execute(
            "SELECT * FROM agent_handoffs WHERE id = ?", (turn["handoff_id"],)
        ).fetchone()
        if h:
            handoff = dict(h)

    return {
        "turn": dict(turn),
        "blocks": [dict(b) for b in blocks],
        "handoff": handoff,
    }


def query_turn_trace(conn, trace_id: str) -> list[dict]:
    """按 trace_id 查询完整的跨 Agent 调用链。"""
    turns = conn.execute(
        "SELECT * FROM conversation_turns WHERE trace_id = ? "
        "ORDER BY time_start ASC",
        (trace_id,),
    ).fetchall()

    handoffs = conn.execute(
        "SELECT * FROM agent_handoffs WHERE trace_id = ? "
        "ORDER BY time_start ASC",
        (trace_id,),
    ).fetchall()

    return {
        "turns": [dict(t) for t in turns],
        "handoffs": [dict(h) for h in handoffs],
    }


def query_turn_tree(conn) -> list[dict]:
    """查询 Agent 日志树结构（按分组层级组织）。

    直接从 conversation_turns 聚合，从全局 agent_id 解析分组和展示名。
    """
    rows = conn.execute(
        "SELECT agent_id, severity, COUNT(*) as turn_count "
        "FROM conversation_turns "
        "GROUP BY agent_id "
        "ORDER BY agent_id"
    ).fetchall()

    # 按分组归并
    groups: dict[str, dict] = {}
    agent_seen: dict[str, bool] = {}
    for r in rows:
        agent_id = r["agent_id"]
        parts = agent_id.split("::")
        display_name = parts[4] if len(parts) >= 6 else agent_id[:30]
        group_name = parts[0] if parts else "默认"

        if agent_id in agent_seen:
            continue
        agent_seen[agent_id] = True

        if group_name not in groups:
            groups[group_name] = {"group": group_name, "agents": [], "total": 0}
        agent_node = {
            "agent_id": agent_id,
            "display_name": display_name,
            "source_name": parts[1] if len(parts) >= 2 else "",
            "status": "active",  # 日志系统不追踪 agent 状态，默认 active
            "turn_count": r["turn_count"],
        }
        groups[group_name]["agents"].append(agent_node)
        groups[group_name]["total"] += r["turn_count"]

    return sorted(groups.values(), key=lambda g: g["group"])


# ── 即时通讯查询 ──

def _json_text(value, default="{}") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            return default
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return default


def _json_value(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _int_or_none(value):
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_attachments(attachments) -> list[dict]:
    if not isinstance(attachments, list):
        return []
    rows = []
    allowed = {"image", "link", "video", "audio", "file", "url"}
    for item in attachments[:20]:
        if isinstance(item, str):
            item = {"type": "link", "url": item}
        if not isinstance(item, dict):
            continue
        attachment_type = (item.get("type") or item.get("attachment_type") or "file").strip().lower()
        if attachment_type not in allowed:
            attachment_type = "file"
        if attachment_type == "url":
            attachment_type = "link"
        rows.append({
            "attachment_type": attachment_type,
            "url": str(item.get("url") or item.get("link") or "")[:2048],
            "title": str(item.get("title") or item.get("name") or "")[:240],
            "mime_type": str(item.get("mime_type") or item.get("mime") or "")[:120],
            "size_bytes": _int_or_none(item.get("size_bytes") or item.get("size")),
            "metadata_json": _json_text(item.get("metadata") or item.get("metadata_json")),
        })
    return rows


def _load_attachments(conn, message_ids: list[int]) -> dict[int, list[dict]]:
    if not message_ids:
        return {}
    placeholders = ",".join("?" for _ in message_ids)
    rows = conn.execute(
        f"SELECT * FROM chat_attachments WHERE message_id IN ({placeholders}) ORDER BY id",
        message_ids,
    ).fetchall()
    by_message: dict[int, list[dict]] = {}
    for row in rows:
        item = dict(row)
        item["type"] = item.get("attachment_type")
        item["metadata"] = _json_value(item.get("metadata_json"), {})
        by_message.setdefault(int(item.get("message_id") or 0), []).append(item)
    return by_message


def _task_card(row) -> dict:
    item = dict(row)
    item["allow_autostart"] = bool(item.get("allow_autostart"))
    item["metadata"] = _json_value(item.get("metadata_json"), {})
    item["required_capabilities"] = _json_value(item.get("required_capabilities_json"), [])
    return {
        "id": item.get("id"),
        "agent_id": item.get("agent_id"),
        "agent_name": item.get("agent_name"),
        "agent_role": item.get("agent_role"),
        "task_type": item.get("task_type"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "title": item.get("title"),
        "body": item.get("body"),
        "source_conversation_id": item.get("source_conversation_id"),
        "source_message_id": item.get("source_message_id"),
        "result_text": item.get("result_text"),
        "error_text": item.get("error_text"),
        "last_error": item.get("last_error"),
        "metadata": item.get("metadata"),
        "required_capabilities": item.get("required_capabilities"),
        "allow_autostart": item.get("allow_autostart"),
        "approval_status": item.get("approval_status") or "not_required",
        "approval_required": bool(item.get("approval_required")),
        "approved_by": item.get("approved_by") or "",
        "approved_at": item.get("approved_at"),
        "rejected_by": item.get("rejected_by") or "",
        "rejected_at": item.get("rejected_at"),
        "rejected_reason": item.get("rejected_reason") or "",
        "claimed_by": item.get("claimed_by"),
        "claimed_at": item.get("claimed_at"),
        "started_at": item.get("started_at"),
        "completed_at": item.get("completed_at"),
        "lease_expires_at": item.get("lease_expires_at"),
        "attempt_count": item.get("attempt_count") or 0,
        "max_attempts": item.get("max_attempts") or 3,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _load_task_events(conn, task_id: int, limit: int = 200) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT * FROM agent_task_events WHERE task_id=? ORDER BY created_at ASC, id ASC LIMIT ?",
            (int(task_id), int(limit)),
        ).fetchall()
    except Exception:
        return []
    events = []
    for row in rows:
        item = dict(row)
        item["data"] = _json_value(item.get("data_json"), {})
        events.append(item)
    return events


def _load_task_cards(conn, message_ids: list[int]) -> dict[int, list[dict]]:
    if not message_ids:
        return {}
    placeholders = ",".join("?" for _ in message_ids)
    try:
        rows = conn.execute(
            f"SELECT * FROM agent_tasks WHERE source_message_id IN ({placeholders}) "
            "ORDER BY priority DESC, created_at ASC",
            message_ids,
        ).fetchall()
    except Exception:
        return {}
    by_message: dict[int, list[dict]] = {}
    for row in rows:
        card = _task_card(row)
        by_message.setdefault(int(card.get("source_message_id") or 0), []).append(card)
    return by_message


def _hydrate_chat_messages(conn, rows) -> list[dict]:
    messages = [dict(row) for row in rows]
    message_ids = [int(m.get("id") or 0) for m in messages]
    attachments = _load_attachments(conn, message_ids)
    task_cards = _load_task_cards(conn, message_ids)
    for msg in messages:
        msg["metadata"] = _json_value(msg.get("metadata_json"), {})
        msg["attachments"] = attachments.get(int(msg.get("id") or 0), [])
        msg["tasks"] = task_cards.get(int(msg.get("id") or 0), [])
        msg["task_count"] = len(msg["tasks"])
    return messages


def _resolve_root_id(conn, reply_to: int | None, root_id: int | None) -> int | None:
    root_id = _int_or_none(root_id)
    if root_id:
        return root_id
    reply_to = _int_or_none(reply_to)
    if not reply_to:
        return None
    parent = conn.execute(
        "SELECT id, root_id FROM chat_messages WHERE id = ?",
        (reply_to,),
    ).fetchone()
    if not parent:
        return reply_to
    return int(parent["root_id"] or parent["id"])


def _pending_task_count(conn, conv_id: int, participant_type: str | None = None,
                        participant_id: str | None = None) -> int:
    try:
        params = [int(conv_id)]
        where = [
            "source_conversation_id = ?",
            "status IN ('queued', 'claimed', 'running')",
        ]
        if participant_type == "agent" and participant_id:
            where.append("agent_id = ?")
            params.append(participant_id)
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM agent_tasks WHERE " + " AND ".join(where),
            tuple(params),
        ).fetchone()
        return int(row["cnt"] or 0) if row else 0
    except Exception:
        return 0


def query_chat_conversations(conn, limit=50, participant_type: str | None = None,
                             participant_id: str | None = None) -> list[dict]:
    """Return conversations, optionally enriched from a participant's channel state."""
    participant_type = (participant_type or "").strip() or None
    participant_id = (participant_id or "").strip() or None
    if participant_type and participant_id:
        rows = conn.execute(
            "SELECT c.id, c.type, c.agent_id, c.title, c.last_message, c.last_time, "
            "COALESCE(m.unread_count, s.unread_count, c.unread_count, 0) AS unread_count, "
            "COALESCE(m.mention_count, s.mention_count, 0) AS mention_count, "
            "COALESCE(m.last_seen_message_id, s.last_seen_message_id, 0) AS last_seen_message_id, "
            "COALESCE(m.role, 'member') AS member_role, "
            "COALESCE(m.muted, 0) AS muted "
            "FROM chat_conversations c "
            "LEFT JOIN chat_conversation_members m ON m.conversation_id=c.id "
            "  AND m.participant_type=? AND m.participant_id=? "
            "LEFT JOIN chat_conversation_state s ON s.conversation_id=c.id "
            "  AND s.participant_type=? AND s.participant_id=? "
            "WHERE m.id IS NOT NULL OR c.type IN ('group', 'system') "
            "  OR (c.type IN ('private', 'dm', 'agent_dm') AND c.agent_id=?) "
            "ORDER BY COALESCE(c.last_time, c.created_at) DESC LIMIT ?",
            (participant_type, participant_id, participant_type, participant_id, participant_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, type, agent_id, title, last_message, last_time, unread_count, "
            "0 AS mention_count, 0 AS last_seen_message_id, 'member' AS member_role, 0 AS muted "
            "FROM chat_conversations ORDER BY COALESCE(last_time, created_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    convs = []
    for row in rows:
        item = dict(row)
        item["pending_task_count"] = _pending_task_count(conn, item["id"], participant_type, participant_id)
        item["task_count"] = item["pending_task_count"]
        convs.append(item)
    return convs


def query_chat_messages(conn, conv_id: int, limit=100, before_id: int | None = None,
                        after_id: int | None = None) -> list[dict]:
    """??????????? before_id/after_id ?????"""
    if after_id:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id = ? AND id > ? "
            "AND COALESCE(deleted_at, 0) = 0 ORDER BY id ASC LIMIT ?",
            (conv_id, after_id, limit),
        ).fetchall()
        return _hydrate_chat_messages(conn, rows)
    if before_id:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id = ? AND id < ? "
            "AND COALESCE(deleted_at, 0) = 0 ORDER BY timestamp DESC LIMIT ?",
            (conv_id, before_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id = ? "
            "AND COALESCE(deleted_at, 0) = 0 ORDER BY timestamp DESC LIMIT ?",
            (conv_id, limit),
        ).fetchall()
    return _hydrate_chat_messages(conn, list(reversed(rows)))


def query_chat_message(conn, message_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM chat_messages WHERE id = ? AND COALESCE(deleted_at, 0) = 0",
        (message_id,),
    ).fetchone()
    if not row:
        return None
    messages = _hydrate_chat_messages(conn, [row])
    return messages[0] if messages else None


def query_chat_thread(conn, message_id: int, limit: int = 100) -> dict | None:
    msg = query_chat_message(conn, message_id)
    if not msg:
        return None
    root_id = int(msg.get("root_id") or msg.get("id") or message_id)
    root = query_chat_message(conn, root_id) or msg
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE COALESCE(deleted_at, 0) = 0 "
        "AND id != ? AND (root_id = ? OR reply_to = ?) "
        "ORDER BY timestamp ASC, id ASC LIMIT ?",
        (root_id, root_id, root_id, limit),
    ).fetchall()
    replies = _hydrate_chat_messages(conn, rows)
    participants = []
    seen = set()
    for item in [root] + replies:
        name = item.get("sender_name") or item.get("sender_id") or ""
        if name and name not in seen:
            seen.add(name)
            participants.append({
                "sender_type": item.get("sender_type"),
                "sender_id": item.get("sender_id"),
                "sender_name": name,
            })
    last_reply_at = max([int(r.get("timestamp") or 0) for r in replies] or [0])
    return {
        "thread_id": root_id,
        "root": root,
        "replies": replies,
        "summary": {
            "reply_count": len(replies),
            "last_reply_at": last_reply_at,
            "participants": participants,
        },
    }


def ensure_chat_conversation_member(conn, conv_id: int, participant_type: str,
                                    participant_id: str, *, display_name: str = "",
                                    role: str = "member", muted: int = 0,
                                    now: int | None = None):
    now = now or int(time.time() * 1000)
    conn.execute(
        "INSERT OR IGNORE INTO chat_conversation_members "
        "(conversation_id, participant_type, participant_id, display_name, role, muted, joined_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (int(conv_id), participant_type, participant_id, display_name or participant_id,
         role or "member", int(bool(muted)), now, now),
    )
    conn.execute(
        "UPDATE chat_conversation_members SET display_name=COALESCE(NULLIF(display_name, ''), ?), "
        "role=COALESCE(NULLIF(role, ''), ?), updated_at=? "
        "WHERE conversation_id=? AND participant_type=? AND participant_id=?",
        (display_name or participant_id, role or "member", now, int(conv_id), participant_type, participant_id),
    )


def ensure_default_chat_members(conn, conv_id: int, now: int | None = None):
    now = now or int(time.time() * 1000)
    conv = conn.execute(
        "SELECT id, type, agent_id, title FROM chat_conversations WHERE id = ?",
        (int(conv_id),),
    ).fetchone()
    if not conv:
        return
    ensure_chat_conversation_member(
        conn, int(conv_id), "human", "tianyu", display_name="\u5929\u5b87",
        role="owner", now=now,
    )
    conv_type = conv["type"] or "group"
    if conv_type in ("private", "dm", "agent_dm") and conv["agent_id"]:
        agent = conn.execute(
            "SELECT id, name, display_name, role FROM agents WHERE id = ?",
            (conv["agent_id"],),
        ).fetchone()
        display = (agent["display_name"] or agent["name"] or agent["id"]) if agent else conv["agent_id"]
        role = agent["role"] if agent else "agent-worker"
        ensure_chat_conversation_member(
            conn, int(conv_id), "agent", conv["agent_id"], display_name=display,
            role=role or "agent-worker", now=now,
        )
    elif conv_type in ("group", "system"):
        rows = conn.execute(
            "SELECT id, name, display_name, role FROM agents WHERE status != 'removed'"
        ).fetchall()
        for row in rows:
            ensure_chat_conversation_member(
                conn, int(conv_id), "agent", row["id"],
                display_name=row["display_name"] or row["name"] or row["id"],
                role=row["role"] or "agent-worker",
                now=now,
            )


def record_chat_mentions(conn, message_id: int, conv_id: int, mentions: list[dict],
                         now: int | None = None):
    now = now or int(time.time() * 1000)
    for mention in mentions or []:
        participant_type = mention.get("participant_type") or "agent"
        participant_id = mention.get("participant_id") or ""
        if not participant_id:
            continue
        targets = [(participant_type, participant_id)]
        if mention.get("mention_type") == "all" and participant_id == "*":
            targets = [
                ("agent", row["participant_id"])
                for row in conn.execute(
                    "SELECT participant_id FROM chat_conversation_members "
                    "WHERE conversation_id=? AND participant_type='agent'",
                    (int(conv_id),),
                ).fetchall()
            ]
        for target_type, target_id in targets:
            if not target_id:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO chat_message_mentions "
                "(message_id, conversation_id, participant_type, participant_id, mention_token, mention_type, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    int(message_id),
                    int(conv_id),
                    target_type,
                    target_id,
                    mention.get("mention_token") or "",
                    mention.get("mention_type") or "direct",
                    now,
                ),
            )


def apply_chat_member_delivery(conn, conv_id: int, msg: dict, mentions: list[dict] | None = None,
                               now: int | None = None):
    now = now or int(time.time() * 1000)
    ensure_default_chat_members(conn, conv_id, now=now)
    msg_id = int(msg.get("id") or 0)
    sender_type = msg.get("sender_type") or "human"
    sender_id = msg.get("sender_id") or ("tianyu" if sender_type != "agent" else "")
    sender_participant_type = "agent" if sender_type == "agent" else "human"
    sender_name = msg.get("sender_name") or sender_id or "\u5929\u5b87"
    if sender_id:
        ensure_chat_conversation_member(
            conn, conv_id, sender_participant_type, sender_id,
            display_name=sender_name, role="member", now=now,
        )
        upsert_chat_conversation_state(
            conn, conv_id, sender_participant_type, sender_id,
            last_seen_message_id=msg_id, now=now,
        )

    mentions = mentions or []
    record_chat_mentions(conn, msg_id, conv_id, mentions, now=now)
    mentioned = {
        (m.get("participant_type") or "agent", m.get("participant_id") or "")
        for m in mentions
        if m.get("mention_type") == "direct"
    }
    mention_all = any(m.get("mention_type") == "all" for m in mentions)

    rows = conn.execute(
        "SELECT participant_type, participant_id FROM chat_conversation_members "
        "WHERE conversation_id=?",
        (int(conv_id),),
    ).fetchall()
    for row in rows:
        participant_type = row["participant_type"]
        participant_id = row["participant_id"]
        if participant_type == sender_participant_type and participant_id == sender_id:
            continue
        is_mentioned = mention_all or (participant_type, participant_id) in mentioned
        upsert_chat_conversation_state(
            conn, conv_id, participant_type, participant_id,
            unread_delta=1,
            mention_delta=1 if is_mentioned else 0,
            urgent_delta=1 if (msg.get("priority") or "").lower() == "urgent" else 0,
            now=now,
        )

    total = conn.execute(
        "SELECT COALESCE(SUM(unread_count), 0) as total FROM chat_conversation_members WHERE conversation_id=?",
        (int(conv_id),),
    ).fetchone()
    conn.execute(
        "UPDATE chat_conversations SET unread_count=? WHERE id=?",
        (int(total["total"] or 0) if total else 0, int(conv_id)),
    )
    conn.commit()


def query_chat_contacts(conn) -> list[dict]:
    """Agent contact list grouped for chat UI."""
    rows = conn.execute(
        "SELECT id, display_name, group_name, agent_type, model_id, status "
        "FROM agents WHERE status != 'removed' AND model_id IS NOT NULL AND model_id != '' "
        "ORDER BY group_name, display_name"
    ).fetchall()
    groups: dict[str, dict] = {}
    for r in rows:
        gn = r["group_name"] or "\u9ed8\u8ba4"
        if gn not in groups:
            groups[gn] = {"group": gn, "agents": [], "online": 0}
        groups[gn]["agents"].append({
            "agent_id": r["id"],
            "display_name": r["display_name"] or r["id"],
            "agent_type": r["agent_type"],
            "model_id": r["model_id"],
            "status": r["status"],
            "avatar": (r["display_name"] or r["id"])[:2].upper(),
        })
        if r["status"] in ("active", "idle", "working"):
            groups[gn]["online"] += 1
    return sorted(groups.values(), key=lambda g: g["group"])


def query_chat_unread_total(conn) -> int:
    """Total unread count used by chat tab badge."""
    row = conn.execute(
        "SELECT COALESCE(SUM(unread_count), 0) as total FROM chat_conversations"
    ).fetchone()
    return row["total"] if row else 0


def query_or_create_conversation(conn, conv_type: str, agent_id: str | None, title: str, now: int) -> dict:
    """Find or create a conversation. Groups are keyed by title; DMs by agent_id."""
    if conv_type in ("private", "dm", "agent_dm") and agent_id:
        row = conn.execute(
            "SELECT * FROM chat_conversations WHERE type IN ('private', 'dm', 'agent_dm') AND agent_id=?",
            (agent_id,),
        ).fetchone()
        if row:
            return dict(row)
    elif conv_type in ("group", "system") and title:
        row = conn.execute(
            "SELECT * FROM chat_conversations WHERE type=? AND title=?",
            (conv_type, title),
        ).fetchone()
        if row:
            return dict(row)

    conn.execute(
        "INSERT INTO chat_conversations (type, agent_id, title, created_at) VALUES (?, ?, ?, ?)",
        (conv_type, agent_id, title, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM chat_conversations WHERE id = last_insert_rowid()").fetchone()
    return dict(row)


def insert_chat_message(conn, conv_id: int, sender_type: str, sender_id: str,
                        sender_name: str, content: str, msg_type: str,
                        reply_to: int | None, now: int,
                        *, root_id: int | None = None,
                        attachments: list | None = None,
                        metadata=None, priority: str = "",
                        is_agent_initiated: int = 0,
                        task_context: str = "",
                        share_type: str = "none") -> dict:
    """???????????????????/??????"""
    reply_to = _int_or_none(reply_to)
    resolved_root_id = _resolve_root_id(conn, reply_to, root_id)
    metadata_json = _json_text(metadata)
    conn.execute(
        "INSERT INTO chat_messages (conversation_id, sender_type, sender_id, sender_name, "
        "content, msg_type, reply_to, root_id, metadata_json, priority, "
        "is_agent_initiated, task_context, share_type, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (conv_id, sender_type, sender_id, sender_name, content, msg_type,
         reply_to, resolved_root_id, metadata_json, priority or "",
         int(bool(is_agent_initiated)), task_context or "", share_type or "none", now),
    )
    msg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for attachment in _normalize_attachments(attachments):
        conn.execute(
            "INSERT INTO chat_attachments (message_id, attachment_type, url, title, "
            "mime_type, size_bytes, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_id, attachment["attachment_type"], attachment["url"], attachment["title"],
             attachment["mime_type"], attachment["size_bytes"], attachment["metadata_json"], now),
        )
    conn.execute(
        "UPDATE chat_conversations SET last_message=?, last_time=?, "
        "unread_count = CASE WHEN ? = 'agent' THEN unread_count + 1 ELSE unread_count END "
        "WHERE id=?",
        (content[:100], now, sender_type, conv_id),
    )
    conn.commit()
    return query_chat_message(conn, msg_id) or {}


def upsert_chat_conversation_state(conn, conv_id: int, participant_type: str,
                                   participant_id: str, *, last_seen_message_id: int | None = None,
                                   unread_delta: int = 0, mention_delta: int = 0,
                                   urgent_delta: int = 0, now: int | None = None):
    now = now or int(time.time() * 1000)
    row = conn.execute(
        "SELECT id, last_seen_message_id, unread_count, mention_count, urgent_count "
        "FROM chat_conversation_state WHERE conversation_id=? AND participant_type=? AND participant_id=?",
        (conv_id, participant_type, participant_id),
    ).fetchone()
    if row:
        last_seen = int(row["last_seen_message_id"] or 0)
        if last_seen_message_id is not None:
            last_seen = max(last_seen, int(last_seen_message_id or 0))
        conn.execute(
            "UPDATE chat_conversation_state SET last_seen_message_id=?, "
            "unread_count=?, mention_count=?, urgent_count=?, updated_at=? WHERE id=?",
            (last_seen,
             max(0, int(row["unread_count"] or 0) + unread_delta),
             max(0, int(row["mention_count"] or 0) + mention_delta),
             max(0, int(row["urgent_count"] or 0) + urgent_delta),
             now, row["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO chat_conversation_state (conversation_id, participant_type, participant_id, "
            "last_seen_message_id, unread_count, mention_count, urgent_count, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conv_id, participant_type, participant_id, int(last_seen_message_id or 0),
             max(0, unread_delta), max(0, mention_delta), max(0, urgent_delta), now),
        )
    member = conn.execute(
        "SELECT id, last_seen_message_id, unread_count, mention_count, task_count "
        "FROM chat_conversation_members WHERE conversation_id=? AND participant_type=? AND participant_id=?",
        (conv_id, participant_type, participant_id),
    ).fetchone()
    if member:
        member_seen = int(member["last_seen_message_id"] or 0)
        if last_seen_message_id is not None:
            member_seen = max(member_seen, int(last_seen_message_id or 0))
        conn.execute(
            "UPDATE chat_conversation_members SET last_seen_message_id=?, unread_count=?, "
            "mention_count=?, updated_at=? WHERE id=?",
            (
                member_seen,
                max(0, int(member["unread_count"] or 0) + unread_delta),
                max(0, int(member["mention_count"] or 0) + mention_delta),
                now,
                member["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO chat_conversation_members "
            "(conversation_id, participant_type, participant_id, display_name, role, "
            "last_seen_message_id, unread_count, mention_count, joined_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'member', ?, ?, ?, ?, ?)",
            (
                conv_id, participant_type, participant_id, participant_id,
                int(last_seen_message_id or 0),
                max(0, unread_delta),
                max(0, mention_delta),
                now,
                now,
            ),
        )


def mark_conversation_read(conn, conv_id: int, participant_type: str | None = None,
                           participant_id: str | None = None):
    max_row = conn.execute(
        "SELECT COALESCE(MAX(id), 0) as last_id FROM chat_messages WHERE conversation_id = ?",
        (conv_id,),
    ).fetchone()
    last_id = int(max_row["last_id"] or 0)
    if participant_type and participant_id:
        upsert_chat_conversation_state(
            conn, conv_id, participant_type, participant_id,
            last_seen_message_id=last_id, unread_delta=0, mention_delta=0, urgent_delta=0,
        )
        conn.execute(
            "UPDATE chat_conversation_state SET unread_count=0, mention_count=0, urgent_count=0 "
            "WHERE conversation_id=? AND participant_type=? AND participant_id=?",
            (conv_id, participant_type, participant_id),
        )
        conn.execute(
            "UPDATE chat_conversation_members SET last_seen_message_id=?, unread_count=0, "
            "mention_count=0, updated_at=? "
            "WHERE conversation_id=? AND participant_type=? AND participant_id=?",
            (last_id, int(time.time() * 1000), conv_id, participant_type, participant_id),
        )
        conn.execute(
            "UPDATE chat_message_mentions SET is_read=1 "
            "WHERE conversation_id=? AND participant_type=? AND participant_id=?",
            (conv_id, participant_type, participant_id),
        )
    else:
        conn.execute(
            "UPDATE chat_conversations SET unread_count = 0 WHERE id = ?", (conv_id,)
        )
    conn.commit()


def query_chat_mentions(conn, participant_type: str = "agent", participant_id: str | None = None,
                        unread_only: bool = False, limit: int = 50) -> list[dict]:
    participant_id = (participant_id or "").strip()
    if not participant_id:
        return []
    clauses = ["m.participant_type = ?", "m.participant_id = ?"]
    params = [participant_type or "agent", participant_id]
    if unread_only:
        clauses.append("m.is_read = 0")
    rows = conn.execute(
        "SELECT m.*, c.title AS conversation_title, c.type AS conversation_type, "
        "msg.sender_type, msg.sender_id, msg.sender_name, msg.content, msg.timestamp, msg.msg_type "
        "FROM chat_message_mentions m "
        "JOIN chat_messages msg ON msg.id = m.message_id "
        "JOIN chat_conversations c ON c.id = m.conversation_id "
        "WHERE " + " AND ".join(clauses) + " "
        "ORDER BY m.created_at DESC LIMIT ?",
        (*params, int(limit)),
    ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["message"] = query_chat_message(conn, int(item["message_id"]))
        item["conversation"] = {
            "id": item.get("conversation_id"),
            "title": item.get("conversation_title"),
            "type": item.get("conversation_type"),
        }
        results.append(item)
    return results


def query_chat_message_context(conn, message_id: int) -> dict | None:
    msg = query_chat_message(conn, int(message_id))
    if not msg:
        return None
    conv = conn.execute(
        "SELECT * FROM chat_conversations WHERE id = ?",
        (int(msg.get("conversation_id") or 0),),
    ).fetchone()
    mentions = conn.execute(
        "SELECT * FROM chat_message_mentions WHERE message_id=? ORDER BY id",
        (int(message_id),),
    ).fetchall()
    inbox = conn.execute(
        "SELECT * FROM inbox WHERE source_message_id=? ORDER BY created_at DESC LIMIT 20",
        (int(message_id),),
    ).fetchall()
    tasks = []
    try:
        rows = conn.execute(
            "SELECT * FROM agent_tasks WHERE source_message_id=? ORDER BY priority DESC, created_at ASC",
            (int(message_id),),
        ).fetchall()
        tasks = [_task_card(row) for row in rows]
        for task in tasks:
            task["events"] = _load_task_events(conn, int(task.get("id") or 0))
    except Exception:
        tasks = []
    return {
        "message": msg,
        "conversation": dict(conv) if conv else None,
        "thread": query_chat_thread(conn, int(message_id)),
        "mentions": [dict(row) for row in mentions],
        "tasks": tasks,
        "inbox": [dict(row) for row in inbox],
    }


# ---- Token Dashboard Queries ----

def query_token_by_day(conn, days: int = 7, agent_id: str = None, model_id: str = None):
    """Daily token aggregates for the last N days."""
    since = int((time.time() - days * 86400) * 1000)
    wheres = ["timestamp >= ?"]
    params = [since]
    if agent_id:
        wheres.append("agent_id = ?")
        params.append(agent_id)
    if model_id:
        wheres.append("model_id = ?")
        params.append(model_id)
    where = " AND ".join(wheres)
    rows = conn.execute(
        f"SELECT date(timestamp / 1000, 'unixepoch') as day, "
        f"COALESCE(SUM(tokens_input), 0) as inp, "
        f"COALESCE(SUM(tokens_output), 0) as outp, "
        f"COALESCE(SUM(cache_read), 0) as cache_r, "
        f"COALESCE(SUM(cache_write), 0) as cache_w, "
        f"COALESCE(SUM(cost), 0) as cost "
        f"FROM token_records WHERE {where} "
        f"GROUP BY day ORDER BY day",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def query_token_by_model(conn, days: int = 7, agent_id: str = None):
    """Token aggregates grouped by model_id."""
    since = int((time.time() - days * 86400) * 1000)
    wheres = ["timestamp >= ?"]
    params = [since]
    if agent_id:
        wheres.append("agent_id = ?")
        params.append(agent_id)
    where = " AND ".join(wheres)
    rows = conn.execute(
        f"SELECT COALESCE(model_id, 'unknown') as model, "
        f"COALESCE(provider_id, 'unknown') as provider, "
        f"COUNT(DISTINCT agent_id) as agent_count, "
        f"COALESCE(SUM(tokens_input), 0) as inp, "
        f"COALESCE(SUM(tokens_output), 0) as outp, "
        f"COALESCE(SUM(cache_read), 0) as cache_r, "
        f"COALESCE(SUM(cache_write), 0) as cache_w, "
        f"COALESCE(SUM(cost), 0) as cost "
        f"FROM token_records WHERE {where} "
        f"GROUP BY model_id ORDER BY cost DESC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def query_token_by_hour(conn, date_str: str, agent_id: str = None):
    """Hourly token distribution for a given date (YYYY-MM-DD)."""
    import datetime
    day_start = int(datetime.datetime.strptime(date_str, "%Y-%m-%d").timestamp() * 1000)
    day_end = day_start + 86400 * 1000
    wheres = ["timestamp >= ?", "timestamp < ?"]
    params = [day_start, day_end]
    if agent_id:
        wheres.append("agent_id = ?")
        params.append(agent_id)
    where = " AND ".join(wheres)
    rows = conn.execute(
        f"SELECT CAST(strftime('%H', timestamp / 1000, 'unixepoch') AS INTEGER) as hour, "
        f"COALESCE(SUM(tokens_input), 0) as inp, "
        f"COALESCE(SUM(tokens_output), 0) as outp, "
        f"COALESCE(SUM(cost), 0) as cost "
        f"FROM token_records WHERE {where} "
        f"GROUP BY hour ORDER BY hour",
        params,
    ).fetchall()
    return [dict(r) for r in rows]

# -- Multica-style dashboard queries --

def query_token_by_agent(conn, days: int = 30):
    since = int((time.time() - days * 86400) * 1000)
    rows = conn.execute(
        "SELECT agent_id, "
        "COALESCE(SUM(tokens_input), 0) as inp, "
        "COALESCE(SUM(tokens_output), 0) as outp, "
        "COALESCE(SUM(cache_read), 0) as cache_r, "
        "COALESCE(SUM(cache_write), 0) as cache_w, "
        "COALESCE(SUM(cost), 0) as cost, "
        "COUNT(DISTINCT message_id) as task_count "
        "FROM token_records WHERE timestamp >= ? "
        "GROUP BY agent_id ORDER BY cost DESC",
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def query_token_rollup(conn, days: int = 30):
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    rows = conn.execute(
        "SELECT date, agent_id, "
        "SUM(tokens_input) as inp, SUM(tokens_output) as outp, "
        "SUM(cache_read) as cache_r, SUM(cache_write) as cache_w, "
        "SUM(total_cost) as cost "
        "FROM daily_stats WHERE date >= ? "
        "GROUP BY date ORDER BY date",
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def query_unmapped_models(conn):
    rows = conn.execute(
        "SELECT DISTINCT tr.model_id, COUNT(*) as record_count, "
        "COALESCE(SUM(tr.tokens_input + tr.tokens_output), 0) as total_tokens "
        "FROM token_records tr "
        "LEFT JOIN pricing p ON p.model_id = tr.model_id AND p.is_active = 1 "
        "WHERE tr.model_id IS NOT NULL AND tr.model_id != '' "
        "AND p.id IS NULL "
        "GROUP BY tr.model_id ORDER BY total_tokens DESC"
    ).fetchall()
    return [dict(r) for r in rows]
