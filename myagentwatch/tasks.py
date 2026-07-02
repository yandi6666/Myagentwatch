"""Task lifecycle helpers for MyAgentWatch."""

import json
import time


VALID_TASK_STATUSES = {
    "queued",
    "dispatched",
    "running",
    "completed",
    "failed",
    "cancelled",
}

TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}

FAILURE_KEYWORDS = (
    "无法完成",
    "不能完成",
    "没法完成",
    "失败",
    "报错",
    "错误",
    "异常",
    "blocked",
    "failed",
    "error",
    "exception",
)

COMPLETION_KEYWORDS = (
    "已完成",
    "完成了",
    "任务完成",
    "交付",
    "写好了",
    "报告好了",
    "方案好了",
    "done",
    "finished",
    "completed",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_dumps(value) -> str:
    if value is None:
        value = {}
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return "{}"


def _row_to_dict(row) -> dict:
    if not row:
        return {}
    data = dict(row)
    try:
        data["metadata"] = json.loads(data.get("metadata") or "{}")
    except json.JSONDecodeError:
        data["metadata"] = {}
    data["tags"] = [t.strip() for t in (data.get("tags") or "").split(",") if t.strip()]
    return data


def _create_record(conn, task_id: int, event_type: str, status: str = "",
                   actor_id: str = "", message: str = "", metadata=None,
                   timestamp: int | None = None):
    ts = timestamp or _now_ms()
    conn.execute(
        """INSERT INTO task_records
           (task_id, event_type, status, actor_id, message, timestamp, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, event_type, status, actor_id, message, ts, _json_dumps(metadata)),
    )


def create_task(conn, title: str, description: str = "", status: str = "queued",
                assigned_agent_id: str = "", parent_task_id: int | None = None,
                session_id: str = "", priority: int = 0, tags=None,
                metadata=None, source_handoff_id: int | None = None,
                actor_id: str = "system") -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("title required")
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"invalid task status: {status}")

    now = _now_ms()
    tag_text = ",".join(tags) if isinstance(tags, list) else (tags or "")
    time_started = now if status in {"dispatched", "running"} else None
    time_completed = now if status in TERMINAL_TASK_STATUSES else None

    conn.execute(
        """INSERT OR IGNORE INTO tasks
           (title, description, status, assigned_agent_id, parent_task_id,
            session_id, priority, tags, source_handoff_id, time_created,
            time_started, time_completed, updated_at, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            title,
            description or "",
            status,
            assigned_agent_id or "",
            parent_task_id,
            session_id or "",
            priority or 0,
            tag_text,
            source_handoff_id,
            now,
            time_started,
            time_completed,
            now,
            _json_dumps(metadata),
        ),
    )

    if source_handoff_id is not None:
        row = conn.execute(
            "SELECT * FROM tasks WHERE source_handoff_id = ?", (source_handoff_id,)
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM tasks WHERE id = last_insert_rowid()").fetchone()

    task = _row_to_dict(row)
    if task:
        existing_records = conn.execute(
            "SELECT COUNT(*) as cnt FROM task_records WHERE task_id = ?",
            (task["id"],),
        ).fetchone()["cnt"]
        if existing_records == 0:
            _create_record(
                conn,
                task["id"],
                "created",
                status,
                actor_id,
                f"任务创建: {title}",
                {"source_handoff_id": source_handoff_id},
                now,
            )
    return task


def list_tasks(conn, status: str | None = None, assigned_agent_id: str | None = None,
               limit: int = 100) -> list[dict]:
    where = []
    params = []
    if status and status != "all":
        if status == "open":
            where.append("status NOT IN ('completed', 'failed', 'cancelled')")
        else:
            where.append("status = ?")
            params.append(status)
    if assigned_agent_id:
        where.append("assigned_agent_id = ?")
        params.append(assigned_agent_id)

    sql = "SELECT * FROM tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY priority DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_task(conn, task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_task_status(conn, task_id: int, status: str, actor_id: str = "",
                       message: str = "", metadata=None,
                       event_type: str = "status_changed") -> dict:
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"invalid task status: {status}")

    current = get_task(conn, task_id)
    if not current:
        raise LookupError("task not found")
    if current["status"] == status:
        return current

    now = _now_ms()
    updates = ["status = ?", "updated_at = ?"]
    params = [status, now]
    if status in {"dispatched", "running"} and not current.get("time_started"):
        updates.append("time_started = ?")
        params.append(now)
    if status in TERMINAL_TASK_STATUSES:
        updates.append("time_completed = ?")
        params.append(now)
    if status == "failed" or event_type == "auto_status_changed":
        signal = metadata if isinstance(metadata, dict) else {}
        merged_metadata = dict(current.get("metadata") or {})
        merged_metadata["auto_tracking"] = merged_metadata.get("auto_tracking", True)
        if event_type == "auto_status_changed":
            merged_metadata["last_auto_tracking"] = {
                "status": status,
                "message": message or f"{current['status']} → {status}",
                "timestamp": now,
                "signal": signal,
            }
        if status == "failed":
            reason = (
                signal.get("failure_reason")
                or signal.get("reason")
                or message
                or f"{current['status']} → failed"
            )
            detail = (
                signal.get("failure_detail")
                or signal.get("content")
                or signal.get("error_output")
                or signal.get("detail")
                or message
                or ""
            )
            merged_metadata["failure"] = {
                "reason": reason,
                "detail": detail,
                "source": signal.get("source") or event_type,
                "actor_id": actor_id,
                "timestamp": now,
                "previous_status": current["status"],
                "signal": signal,
            }
        updates.append("metadata = ?")
        params.append(_json_dumps(merged_metadata))

    params.append(task_id)
    conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
    _create_record(
        conn,
        task_id,
        event_type,
        status,
        actor_id,
        message or f"{current['status']} → {status}",
        metadata,
        now,
    )
    return get_task(conn, task_id)


def _message_mentions_task(content: str, task: dict, unique_open_for_agent: bool) -> bool:
    text = (content or "").lower()
    if not text:
        return False
    task_id = str(task.get("id", ""))
    title = (task.get("title") or "").strip().lower()
    refs = [
        f"#{task_id}",
        f"任务#{task_id}",
        f"任务 #{task_id}",
        f"task #{task_id}",
        f"task {task_id}",
    ]
    if any(ref in text for ref in refs):
        return True
    if title and len(title) >= 8 and title[:18] in text:
        return True
    # If the agent only has one open task, its status report can be safely
    # treated as referring to that task even without an explicit #id.
    return unique_open_for_agent


def _status_from_agent_message(conn, task: dict, since_ms: int,
                               unique_open_for_agent: bool) -> tuple[str, str, dict] | None:
    agent_id = task.get("assigned_agent_id") or ""
    if not agent_id:
        return None

    agent = conn.execute(
        "SELECT id, name, display_name FROM agents WHERE id = ?",
        (agent_id,),
    ).fetchone()
    names = {agent_id}
    if agent:
        names.update(v for v in (agent["name"], agent["display_name"]) if v)

    rows = conn.execute(
        """SELECT id, sender_id, sender_name, content, msg_type, share_type, timestamp
           FROM chat_messages
           WHERE sender_type = 'agent' AND timestamp >= ?
           ORDER BY timestamp DESC LIMIT 80""",
        (since_ms,),
    ).fetchall()

    for row in rows:
        sender_id = row["sender_id"] or ""
        sender_name = row["sender_name"] or ""
        if sender_id not in names and sender_name not in names:
            continue
        content = row["content"] or ""
        if not _message_mentions_task(content, task, unique_open_for_agent):
            continue

        lower = content.lower()
        meta = {
            "source": "chat_message",
            "message_id": row["id"],
            "timestamp": row["timestamp"],
        }
        # Failure first: phrases like "无法完成" also contain "完成".
        if any(k in lower for k in FAILURE_KEYWORDS):
            return "failed", f"自动追踪：{sender_name or sender_id} 在群聊中报告失败", meta
        if row["msg_type"] == "task_result" or row["share_type"] in {"result", "completion"}:
            return "completed", f"自动追踪：{sender_name or sender_id} 分享了任务结果", meta
        if any(k in lower for k in COMPLETION_KEYWORDS):
            return "completed", f"自动追踪：{sender_name or sender_id} 在群聊中报告完成", meta

    return None


def auto_track_tasks(conn, heartbeat_timeout_sec: int = 300,
                     limit: int = 200) -> list[dict]:
    """Infer task status from Agent signals instead of relying on humans.

    Signals currently used:
    - assigned Agent reports working -> queued/dispatched task becomes running
    - assigned Agent reports blocked/error/offline while running -> task fails
    - assigned Agent sends a matching chat/share result -> task completes/fails
    - source handoff status changes -> task follows the handoff
    """
    now = _now_ms()
    offline_cutoff = now - heartbeat_timeout_sec * 2 * 1000
    changed: list[dict] = []

    rows = conn.execute(
        """SELECT * FROM tasks
           WHERE status NOT IN ('completed', 'failed', 'cancelled')
           ORDER BY priority DESC, updated_at ASC LIMIT ?""",
        (limit,),
    ).fetchall()
    tasks = [_row_to_dict(r) for r in rows]
    open_by_agent: dict[str, int] = {}
    for task in tasks:
        aid = task.get("assigned_agent_id") or ""
        if aid:
            open_by_agent[aid] = open_by_agent.get(aid, 0) + 1

    for task in tasks:
        metadata = task.get("metadata") or {}
        if metadata.get("auto_tracking") is False:
            continue

        task_id = task["id"]
        assigned_agent_id = task.get("assigned_agent_id") or ""
        since = task.get("time_started") or task.get("updated_at") or task.get("time_created") or 0
        unique_open = bool(assigned_agent_id and open_by_agent.get(assigned_agent_id, 0) == 1)

        target_status = ""
        message = ""
        meta = {"auto": True, "previous_status": task["status"]}

        # Handoff-backed tasks should follow their source handoff.
        if task.get("source_handoff_id"):
            handoff = conn.execute(
                "SELECT status, time_end FROM agent_handoffs WHERE id = ?",
                (task["source_handoff_id"],),
            ).fetchone()
            if handoff and handoff["status"] in {"completed", "failed", "cancelled", "running"}:
                mapped = "failed" if handoff["status"] == "error" else handoff["status"]
                if mapped != task["status"]:
                    target_status = mapped
                    message = f"自动追踪：handoff 状态变为 {handoff['status']}"
                    meta.update({"source": "handoff", "handoff_id": task["source_handoff_id"]})

        # Agent chat/share messages are the strongest explicit signal.
        if not target_status:
            msg_signal = _status_from_agent_message(conn, task, since, unique_open)
            if msg_signal:
                target_status, message, msg_meta = msg_signal
                meta.update(msg_meta)

        # Agent state is a weaker but still useful signal.
        if not target_status and assigned_agent_id:
            agent = conn.execute(
                """SELECT status, last_heartbeat_at, last_seen_time
                   FROM agents WHERE id = ?""",
                (assigned_agent_id,),
            ).fetchone()
            if agent:
                agent_status = agent["status"] or ""
                last_signal = max(agent["last_heartbeat_at"] or 0, agent["last_seen_time"] or 0)
                meta.update({
                    "source": "agent_status",
                    "agent_status": agent_status,
                    "last_signal": last_signal,
                })
                if task["status"] in {"queued", "dispatched"} and agent_status == "working":
                    target_status = "running"
                    message = "自动追踪：指派 Agent 已进入 working 状态"
                elif task["status"] == "running" and agent_status in {"error", "blocked"}:
                    target_status = "failed"
                    message = f"自动追踪：指派 Agent 状态为 {agent_status}"
                # Offline means the agent is unreachable, not that the task has
                # failed. Keep the task open until an explicit failure/result
                # signal appears in chat, handoff, or agent error state.

        if target_status and target_status != task["status"]:
            updated = update_task_status(
                conn,
                task_id,
                target_status,
                actor_id="auto-tracker",
                message=message,
                metadata=meta,
                event_type="auto_status_changed",
            )
            changed.append(updated)

    return changed


def task_timeline(conn, task_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM task_records WHERE task_id = ? ORDER BY timestamp ASC",
        (task_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.get("metadata") or "{}")
        except json.JSONDecodeError:
            item["metadata"] = {}
        result.append(item)
    return result


def create_tasks_from_handoffs(conn) -> int:
    """Create task records from agent_handoffs that do not have tasks yet."""
    rows = conn.execute(
        """SELECT h.* FROM agent_handoffs h
           LEFT JOIN tasks t ON t.source_handoff_id = h.id
           WHERE t.id IS NULL
           ORDER BY h.time_start ASC
           LIMIT 200"""
    ).fetchall()
    created = 0
    for h in rows:
        prompt = (h["prompt_text"] or "").strip()
        title = prompt.splitlines()[0][:80] if prompt else f"Handoff to {h['to_agent_id']}"
        status = h["status"] or "queued"
        if status not in VALID_TASK_STATUSES:
            status = "running" if status in {"started", "running"} else "queued"
        create_task(
            conn,
            title=title,
            description=prompt,
            status=status,
            assigned_agent_id=h["to_agent_id"] or "",
            session_id=h["session_id"] or "",
            tags=["handoff"],
            source_handoff_id=h["id"],
            metadata={
                "trace_id": h["trace_id"],
                "from_agent_id": h["from_agent_id"],
                "subagent_type": h["subagent_type"],
            },
            actor_id=h["from_agent_id"] or "collector",
        )
        created += 1
    return created
