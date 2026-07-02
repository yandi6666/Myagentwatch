"""Agent task queue and v3 permission helpers."""

from __future__ import annotations

import json
import time
from typing import Iterable

from myagentwatch.queries import insert_chat_message

DEFAULT_HUMAN_ID = "tianyu"
DEFAULT_HUMAN_NAME = "\u5929\u5b87"
DEFAULT_AGENT_ID = "codex:codex:codex"

CAP_CHAT = "can_chat_with_agent"
CAP_REPLY = "can_request_agent_reply"
CAP_TASK = "can_request_agent_task"
CAP_CODE = "can_request_code_change"
CAP_SHELL = "can_request_shell_command"
CAP_AUTOSTART = "can_autostart_agent"
CAP_MANAGE_PERMS = "can_manage_permissions"

ALL_CAPABILITIES = (
    CAP_CHAT,
    CAP_REPLY,
    CAP_TASK,
    CAP_CODE,
    CAP_SHELL,
    CAP_AUTOSTART,
    CAP_MANAGE_PERMS,
)

USER_ROLE_CAPABILITIES = {
    "user-owner": {
        CAP_CHAT: True,
        CAP_REPLY: True,
        CAP_TASK: True,
        CAP_CODE: True,
        CAP_SHELL: True,
        CAP_AUTOSTART: True,
        CAP_MANAGE_PERMS: True,
    },
    "user-admin": {
        CAP_CHAT: True,
        CAP_REPLY: True,
        CAP_TASK: False,
        CAP_CODE: False,
        CAP_SHELL: False,
        CAP_AUTOSTART: False,
        CAP_MANAGE_PERMS: True,
    },
    "user-member": {
        CAP_CHAT: True,
        CAP_REPLY: True,
        CAP_TASK: False,
        CAP_CODE: False,
        CAP_SHELL: False,
        CAP_AUTOSTART: False,
        CAP_MANAGE_PERMS: False,
    },
    "user-viewer": {
        CAP_CHAT: False,
        CAP_REPLY: False,
        CAP_TASK: False,
        CAP_CODE: False,
        CAP_SHELL: False,
        CAP_AUTOSTART: False,
        CAP_MANAGE_PERMS: False,
    },
    "user-custom": {},
}

AGENT_ROLE_CAPABILITIES = {
    "agent-root": {
        CAP_CHAT: True,
        CAP_REPLY: True,
        CAP_TASK: True,
        CAP_CODE: True,
        CAP_SHELL: True,
        CAP_AUTOSTART: True,
        CAP_MANAGE_PERMS: True,
    },
    "agent-operator": {
        CAP_CHAT: True,
        CAP_REPLY: True,
        CAP_TASK: True,
        CAP_CODE: False,
        CAP_SHELL: False,
        CAP_AUTOSTART: False,
        CAP_MANAGE_PERMS: False,
    },
    "agent-worker": {
        CAP_CHAT: True,
        CAP_REPLY: True,
        CAP_TASK: False,
        CAP_CODE: False,
        CAP_SHELL: False,
        CAP_AUTOSTART: False,
        CAP_MANAGE_PERMS: False,
    },
    "agent-observer": {
        CAP_CHAT: False,
        CAP_REPLY: False,
        CAP_TASK: False,
        CAP_CODE: False,
        CAP_SHELL: False,
        CAP_AUTOSTART: False,
        CAP_MANAGE_PERMS: False,
    },
    "agent-custom": {},
}

TASK_REQUIRED_CAPABILITIES = {
    "reply": [CAP_REPLY],
    "review": [CAP_TASK],
    "code_change": [CAP_CODE],
    "shell_command": [CAP_SHELL],
    "custom": [CAP_TASK],
}

TASK_PRIORITY = {
    "reply": 10,
    "review": 30,
    "code_change": 50,
    "shell_command": 70,
    "custom": 20,
}

APPROVAL_NOT_REQUIRED = "not_required"
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_STATUSES = {
    APPROVAL_NOT_REQUIRED,
    APPROVAL_PENDING,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
}
APPROVAL_CLAIMABLE = {APPROVAL_NOT_REQUIRED, APPROVAL_APPROVED}
TASKS_REQUIRING_APPROVAL = {"review", "code_change", "shell_command", "custom"}


def now_ms() -> int:
    return int(time.time() * 1000)


def _json_load(value, default):
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except Exception:
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _json_text(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _list_json_text(value) -> str:
    return json.dumps(list(value or []), ensure_ascii=False)


def normalize_user_id(user_id: str | None, user_name: str | None = None) -> str:
    user_id = (user_id or "").strip()
    user_name = (user_name or "").strip()
    if user_id:
        return DEFAULT_HUMAN_ID if user_id == DEFAULT_HUMAN_NAME else user_id
    if user_name == DEFAULT_HUMAN_NAME:
        return DEFAULT_HUMAN_ID
    return DEFAULT_HUMAN_ID


def _role_caps(role: str, custom_json: str | None, kind: str) -> dict:
    if kind == "agent":
        base = dict(AGENT_ROLE_CAPABILITIES.get(role or "agent-worker", {}))
    else:
        base = dict(USER_ROLE_CAPABILITIES.get(role or "user-member", {}))
    custom = _json_load(custom_json, {})
    for cap in ALL_CAPABILITIES:
        if cap in custom:
            base[cap] = bool(custom[cap])
    return base


def get_user_profile(conn, user_id: str | None = None, user_name: str | None = None) -> dict:
    normalized = normalize_user_id(user_id, user_name)
    row = conn.execute(
        "SELECT id, name, role, permissions_json FROM users WHERE id = ? OR name = ?",
        (normalized, user_name or ""),
    ).fetchone()
    if row:
        role = row["role"] or ("user-owner" if row["id"] == DEFAULT_HUMAN_ID else "user-member")
        caps = _role_caps(role, row["permissions_json"], "user")
        return {
            "id": row["id"],
            "name": row["name"],
            "role": role,
            "capabilities": caps,
        }
    role = "user-owner" if normalized == DEFAULT_HUMAN_ID else "user-member"
    return {
        "id": normalized,
        "name": user_name or normalized,
        "role": role,
        "capabilities": _role_caps(role, None, "user"),
    }


def get_agent_profile(conn, agent_id: str) -> dict:
    row = conn.execute(
        "SELECT id, name, display_name, role, permissions_json FROM agents WHERE id = ?",
        (agent_id,),
    ).fetchone()
    if row:
        role = row["role"] or ("agent-root" if row["id"] == DEFAULT_AGENT_ID else "agent-worker")
        caps = _role_caps(role, row["permissions_json"], "agent")
        return {
            "id": row["id"],
            "name": row["display_name"] or row["name"] or row["id"],
            "role": role,
            "capabilities": caps,
        }
    role = "agent-root" if agent_id == DEFAULT_AGENT_ID else "agent-worker"
    return {
        "id": agent_id,
        "name": agent_id.split(":")[1] if ":" in agent_id else agent_id,
        "role": role,
        "capabilities": _role_caps(role, None, "agent"),
    }


def required_capabilities(task_type: str) -> list[str]:
    return TASK_REQUIRED_CAPABILITIES.get(task_type or "custom", TASK_REQUIRED_CAPABILITIES["custom"])


def default_approval_for_task(task_type: str) -> tuple[int, str]:
    if task_type in TASKS_REQUIRING_APPROVAL:
        return 1, APPROVAL_PENDING
    return 0, APPROVAL_NOT_REQUIRED


def _missing_capabilities(profile: dict, caps: Iterable[str]) -> list[str]:
    have = profile.get("capabilities") or {}
    return [cap for cap in caps if not have.get(cap)]


def infer_task_type_from_content(content: str, default: str = "reply") -> tuple[str, str | None, str]:
    """Return (task_type, explicit_agent_name, task_body)."""
    text = (content or "").strip()
    lowered = text.lower()
    command_map = {
        "/assign": "review",
        "/run": "custom",
        "/code": "code_change",
        "/shell": "shell_command",
    }
    for command, task_type in command_map.items():
        if lowered == command or lowered.startswith(command + " "):
            rest = text[len(command):].strip()
            if not rest:
                return task_type, None, ""
            parts = rest.split(maxsplit=1)
            target = parts[0].lstrip("@")
            body = parts[1] if len(parts) > 1 else ""
            return task_type, target, body
    return default, None, text


def find_agent_by_name(conn, target: str | None) -> dict | None:
    if not target:
        return None
    normalized = target.strip().lstrip("@").lower()
    if not normalized:
        return None
    rows = conn.execute(
        "SELECT id, name, display_name, role, permissions_json FROM agents WHERE status != 'removed'"
    ).fetchall()
    for row in rows:
        candidates = {row["id"].lower(), (row["name"] or "").lower(), (row["display_name"] or "").lower()}
        if normalized in candidates:
            return dict(row)
    return None


def task_row_to_dict(row) -> dict:
    item = dict(row)
    item["required_capabilities"] = _json_load(item.get("required_capabilities_json"), [])
    item["metadata"] = _json_load(item.get("metadata_json"), {})
    item["display_agent_role"] = f"{item.get('agent_role') or 'agent-worker'}/{item.get('agent_name') or item.get('agent_id')}"
    item["allow_autostart"] = bool(item.get("allow_autostart"))
    item["approval_required"] = bool(item.get("approval_required"))
    status = item.get("approval_status") or APPROVAL_NOT_REQUIRED
    item["approval_status"] = status if status in APPROVAL_STATUSES else APPROVAL_NOT_REQUIRED
    return item


def record_agent_task_event(
    conn,
    task_id: int,
    event_type: str,
    *,
    actor_id: str = "",
    message: str = "",
    data: dict | None = None,
    now: int | None = None,
) -> dict:
    now = now or now_ms()
    conn.execute(
        "INSERT INTO agent_task_events (task_id, event_type, actor_id, message, data_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (int(task_id), event_type, actor_id or "", message or "", _json_text(data or {}), now),
    )
    row = conn.execute("SELECT * FROM agent_task_events WHERE id = last_insert_rowid()").fetchone()
    item = dict(row)
    item["data"] = _json_load(item.get("data_json"), {})
    return item


def list_agent_task_events(conn, task_id: int, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM agent_task_events WHERE task_id=? ORDER BY created_at ASC, id ASC LIMIT ?",
        (int(task_id), int(limit)),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["data"] = _json_load(item.get("data_json"), {})
        items.append(item)
    return items


def recover_expired_agent_tasks(conn, *, now: int | None = None) -> int:
    now = now or now_ms()
    rows = conn.execute(
        "SELECT * FROM agent_tasks WHERE status IN ('claimed', 'running') "
        "AND lease_expires_at IS NOT NULL AND lease_expires_at > 0 AND lease_expires_at < ?",
        (now,),
    ).fetchall()
    recovered = 0
    for row in rows:
        task = task_row_to_dict(row)
        attempts = int(task.get("attempt_count") or 0)
        max_attempts = int(task.get("max_attempts") or 3)
        if attempts >= max_attempts:
            conn.execute(
                "UPDATE agent_tasks SET status='failed', completed_at=?, last_error=?, "
                "error_text=?, lease_expires_at=NULL, updated_at=? WHERE id=?",
                (now, "lease_expired_max_attempts", "lease expired after max attempts", now, task["id"]),
            )
            record_agent_task_event(
                conn,
                task["id"],
                "failed",
                actor_id="system",
                message="lease expired after max attempts",
                data={"attempt_count": attempts, "max_attempts": max_attempts},
                now=now,
            )
        else:
            conn.execute(
                "UPDATE agent_tasks SET status='queued', claimed_by='', claimed_at=NULL, started_at=NULL, "
                "lease_expires_at=NULL, last_error=?, updated_at=? WHERE id=?",
                ("lease_expired_requeued", now, task["id"]),
            )
            record_agent_task_event(
                conn,
                task["id"],
                "requeued",
                actor_id="system",
                message="lease expired; task returned to queue",
                data={"attempt_count": attempts, "max_attempts": max_attempts},
                now=now,
            )
            recovered += 1
    if rows:
        conn.commit()
    return recovered


def create_agent_task(
    conn,
    *,
    agent_id: str,
    task_type: str = "reply",
    title: str = "",
    body: str = "",
    requester_id: str = "",
    requester_name: str = DEFAULT_HUMAN_NAME,
    requester_type: str = "user",
    source_conversation_id: int | None = None,
    source_message_id: int | None = None,
    source_title: str = "",
    metadata: dict | None = None,
    priority: int | None = None,
) -> tuple[dict | None, str | None]:
    """Create a queued agent task after enforcing v3 capability rules."""
    task_type = task_type if task_type in TASK_REQUIRED_CAPABILITIES else "custom"
    requester = get_user_profile(conn, requester_id, requester_name)
    agent = get_agent_profile(conn, agent_id)
    caps = required_capabilities(task_type)
    missing = _missing_capabilities(requester, caps)
    if missing:
        return None, "missing_capability:" + ",".join(missing)

    if source_message_id:
        existing = conn.execute(
            "SELECT * FROM agent_tasks WHERE agent_id=? AND source_message_id=? AND task_type=? "
            "AND status IN ('queued', 'claimed', 'running', 'completed')",
            (agent_id, source_message_id, task_type),
        ).fetchone()
        if existing:
            return task_row_to_dict(existing), None

    allow_autostart = bool(
        task_type == "reply"
        and requester.get("capabilities", {}).get(CAP_AUTOSTART)
    )
    denied_reason = "" if allow_autostart else "autostart_not_allowed_by_role_or_task_type"
    now = now_ms()
    required_json = _list_json_text(caps)
    metadata_json = _json_text(metadata)
    approval_required, approval_status = default_approval_for_task(task_type)
    conn.execute(
        "INSERT INTO agent_tasks (agent_id, agent_name, agent_role, requester_type, requester_id, "
        "requester_name, requester_role, task_type, status, priority, title, body, "
        "source_conversation_id, source_message_id, source_title, required_capability, "
        "required_capabilities_json, allow_autostart, autostart_denied_reason, metadata_json, "
        "approval_status, approval_required, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            agent_id,
            agent["name"],
            agent["role"],
            requester_type,
            requester["id"],
            requester["name"],
            requester["role"],
            task_type,
            priority if priority is not None else TASK_PRIORITY.get(task_type, 0),
            title or f"{task_type}: {agent['name']}",
            body or "",
            source_conversation_id,
            source_message_id,
            source_title or "",
            caps[0] if caps else "",
            required_json,
            1 if allow_autostart else 0,
            denied_reason,
            metadata_json,
            approval_status,
            approval_required,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM agent_tasks WHERE id = last_insert_rowid()").fetchone()
    task_id = int(row["id"])
    record_agent_task_event(
        conn,
        task_id,
        "created",
        actor_id=requester["id"],
        message=title or f"{task_type}: {agent['name']}",
        data={
            "source_conversation_id": source_conversation_id,
            "source_message_id": source_message_id,
            "approval_status": approval_status,
            "approval_required": bool(approval_required),
        },
        now=now,
    )
    conn.commit()
    return task_row_to_dict(row), None


def list_agent_tasks(conn, *, agent_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    clauses = []
    params = []
    if agent_id:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM agent_tasks {where} ORDER BY priority DESC, created_at ASC LIMIT ?",
        (*params, int(limit)),
    ).fetchall()
    return [task_row_to_dict(row) for row in rows]


def get_agent_task(conn, task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
    return task_row_to_dict(row) if row else None


def claim_agent_task(
    conn,
    *,
    agent_id: str,
    claimed_by: str,
    task_id: int | None = None,
    allowed_task_types: list[str] | None = None,
    lease_seconds: int = 300,
) -> dict | None:
    now = now_ms()
    recover_expired_agent_tasks(conn, now=now)
    allowed_task_types = [t for t in (allowed_task_types or []) if t in TASK_REQUIRED_CAPABILITIES]
    params: list = [agent_id]
    placeholders = ",".join("?" for _ in APPROVAL_CLAIMABLE)
    params.extend(sorted(APPROVAL_CLAIMABLE))
    clauses = [
        "agent_id = ?",
        "status = 'queued'",
        "allow_autostart = 1",
        f"COALESCE(approval_status, '{APPROVAL_NOT_REQUIRED}') IN ({placeholders})",
    ]
    if task_id:
        clauses.append("id = ?")
        params.append(int(task_id))
    if allowed_task_types:
        placeholders = ",".join("?" for _ in allowed_task_types)
        clauses.append(f"task_type IN ({placeholders})")
        params.extend(allowed_task_types)
    row = conn.execute(
        "SELECT * FROM agent_tasks WHERE " + " AND ".join(clauses) +
        " ORDER BY priority DESC, created_at ASC LIMIT 1",
        tuple(params),
    ).fetchone()
    if not row:
        return None
    lease_expires_at = now + max(30, int(lease_seconds or 300)) * 1000
    cur = conn.execute(
        "UPDATE agent_tasks SET status='claimed', claimed_by=?, claimed_at=?, "
        "lease_expires_at=?, attempt_count=COALESCE(attempt_count, 0) + 1, updated_at=? "
        "WHERE id=? AND status='queued'",
        (claimed_by, now, lease_expires_at, now, row["id"]),
    )
    if cur.rowcount <= 0:
        return None
    record_agent_task_event(
        conn,
        int(row["id"]),
        "claimed",
        actor_id=claimed_by,
        message=f"claimed by {claimed_by}",
        data={"lease_expires_at": lease_expires_at},
        now=now,
    )
    conn.commit()
    return get_agent_task(conn, int(row["id"]))


def approve_agent_task(conn, task_id: int, actor_id: str = "", actor_name: str = "") -> dict | None:
    now = now_ms()
    current = get_agent_task(conn, int(task_id))
    if not current:
        return None
    cur = conn.execute(
        "UPDATE agent_tasks SET approval_status=?, approved_by=?, approved_at=?, "
        "rejected_by='', rejected_at=NULL, rejected_reason='', updated_at=? "
        "WHERE id=? AND status IN ('queued', 'claimed', 'running')",
        (APPROVAL_APPROVED, actor_id or actor_name or "user", now, now, int(task_id)),
    )
    if cur.rowcount <= 0:
        conn.commit()
        return get_agent_task(conn, int(task_id))
    record_agent_task_event(
        conn,
        int(task_id),
        "approved",
        actor_id=actor_id or actor_name or "user",
        message=f"approved by {actor_name or actor_id or 'user'}",
        data={"approval_status": APPROVAL_APPROVED},
        now=now,
    )
    conn.commit()
    return get_agent_task(conn, int(task_id))


def reject_agent_task(
    conn,
    task_id: int,
    actor_id: str = "",
    actor_name: str = "",
    reason: str = "",
) -> dict | None:
    now = now_ms()
    current = get_agent_task(conn, int(task_id))
    if not current:
        return None
    cur = conn.execute(
        "UPDATE agent_tasks SET approval_status=?, rejected_by=?, rejected_at=?, "
        "rejected_reason=?, updated_at=? "
        "WHERE id=? AND status IN ('queued', 'claimed')",
        (APPROVAL_REJECTED, actor_id or actor_name or "user", now, reason or "", now, int(task_id)),
    )
    if cur.rowcount <= 0:
        conn.commit()
        return get_agent_task(conn, int(task_id))
    record_agent_task_event(
        conn,
        int(task_id),
        "rejected",
        actor_id=actor_id or actor_name or "user",
        message=(reason or f"rejected by {actor_name or actor_id or 'user'}")[:500],
        data={"approval_status": APPROVAL_REJECTED, "reason": reason or ""},
        now=now,
    )
    conn.commit()
    return get_agent_task(conn, int(task_id))


def retry_agent_task(conn, task_id: int, actor_id: str = "", actor_name: str = "") -> dict | None:
    now = now_ms()
    current = get_agent_task(conn, int(task_id))
    if not current:
        return None
    if current.get("status") not in ("failed", "cancelled") and current.get("approval_status") != APPROVAL_REJECTED:
        return current
    approval_required = bool(current.get("approval_required"))
    approval_status = APPROVAL_PENDING if approval_required else APPROVAL_NOT_REQUIRED
    cur = conn.execute(
        "UPDATE agent_tasks SET status='queued', claimed_by='', claimed_at=NULL, started_at=NULL, "
        "completed_at=NULL, lease_expires_at=NULL, result_text='', error_text='', last_error='', "
        "approval_status=?, approved_by='', approved_at=NULL, rejected_by='', rejected_at=NULL, "
        "rejected_reason='', updated_at=? WHERE id=?",
        (approval_status, now, int(task_id)),
    )
    if cur.rowcount <= 0:
        conn.commit()
        return get_agent_task(conn, int(task_id))
    record_agent_task_event(
        conn,
        int(task_id),
        "retried",
        actor_id=actor_id or actor_name or "user",
        message=f"retried by {actor_name or actor_id or 'user'}",
        data={"approval_status": approval_status},
        now=now,
    )
    conn.commit()
    return get_agent_task(conn, int(task_id))


def start_agent_task(conn, task_id: int, actor_id: str = "") -> dict | None:
    now = now_ms()
    current = get_agent_task(conn, int(task_id))
    if not current:
        return None
    cur = conn.execute(
        "UPDATE agent_tasks SET status='running', started_at=?, updated_at=? "
        "WHERE id=? AND status IN ('claimed', 'queued')",
        (now, now, int(task_id)),
    )
    if cur.rowcount <= 0:
        conn.commit()
        return get_agent_task(conn, int(task_id))
    record_agent_task_event(
        conn,
        int(task_id),
        "started",
        actor_id=actor_id or current.get("claimed_by") or "",
        message="task started",
        now=now,
    )
    if current.get("source_conversation_id") and current.get("source_message_id"):
        insert_chat_message(
            conn,
            int(current["source_conversation_id"]),
            "agent",
            current["agent_id"],
            current.get("agent_name") or current["agent_id"],
            f"{current.get('agent_name') or current['agent_id']} 已开始处理任务 #{task_id}",
            "task_status",
            current.get("source_message_id"),
            now,
            root_id=current.get("source_message_id"),
            metadata={"agent_task_id": int(task_id), "event_type": "started"},
            is_agent_initiated=1,
            task_context=current.get("title") or "",
            share_type="status",
        )
    else:
        conn.commit()
    return get_agent_task(conn, int(task_id))


def complete_agent_task(conn, task_id: int, result_text: str, metadata: dict | None = None) -> dict | None:
    now = now_ms()
    current = get_agent_task(conn, int(task_id))
    if not current:
        return None
    merged_metadata = current.get("metadata") or {}
    merged_metadata.update(metadata or {})
    cur = conn.execute(
        "UPDATE agent_tasks SET status='completed', completed_at=?, result_text=?, "
        "metadata_json=?, lease_expires_at=NULL, updated_at=? WHERE id=? AND status IN ('claimed', 'running')",
        (now, result_text or "", _json_text(merged_metadata), now, int(task_id)),
    )
    if cur.rowcount <= 0:
        conn.commit()
        return get_agent_task(conn, int(task_id))
    record_agent_task_event(
        conn,
        int(task_id),
        "completed",
        actor_id=current.get("claimed_by") or current.get("agent_id") or "",
        message=(result_text or "")[:500],
        data=metadata or {},
        now=now,
    )
    if result_text and current.get("source_conversation_id"):
        insert_chat_message(
            conn,
            int(current["source_conversation_id"]),
            "agent",
            current["agent_id"],
            current.get("agent_name") or current["agent_id"],
            result_text,
            "task_result",
            current.get("source_message_id"),
            now,
            root_id=current.get("source_message_id"),
            metadata={"agent_task_id": int(task_id), "task_type": current.get("task_type")},
            priority="",
            is_agent_initiated=1,
            task_context=current.get("title") or "",
            share_type="result",
        )
    else:
        conn.commit()
    return get_agent_task(conn, int(task_id))


def fail_agent_task(conn, task_id: int, error_text: str) -> dict | None:
    now = now_ms()
    current = get_agent_task(conn, int(task_id))
    if not current:
        return None
    cur = conn.execute(
        "UPDATE agent_tasks SET status='failed', completed_at=?, error_text=?, "
        "last_error=?, lease_expires_at=NULL, updated_at=? "
        "WHERE id=? AND status IN ('queued', 'claimed', 'running')",
        (now, error_text or "", error_text or "", now, int(task_id)),
    )
    if cur.rowcount <= 0:
        conn.commit()
        return get_agent_task(conn, int(task_id))
    record_agent_task_event(
        conn,
        int(task_id),
        "failed",
        actor_id=current.get("claimed_by") or "",
        message=(error_text or "")[:500],
        now=now,
    )
    if current.get("source_conversation_id") and current.get("source_message_id"):
        insert_chat_message(
            conn,
            int(current["source_conversation_id"]),
            "agent",
            current["agent_id"],
            current.get("agent_name") or current["agent_id"],
            f"任务 #{task_id} 失败: {(error_text or '')[:240]}",
            "task_status",
            current.get("source_message_id"),
            now,
            root_id=current.get("source_message_id"),
            metadata={"agent_task_id": int(task_id), "event_type": "failed"},
            is_agent_initiated=1,
            task_context=current.get("title") or "",
            share_type="status",
        )
    else:
        conn.commit()
    return get_agent_task(conn, int(task_id))


def cancel_agent_task(conn, task_id: int, actor_id: str = "") -> dict | None:
    now = now_ms()
    current = get_agent_task(conn, int(task_id))
    if not current:
        return None
    cur = conn.execute(
        "UPDATE agent_tasks SET status='cancelled', completed_at=?, error_text=?, "
        "lease_expires_at=NULL, updated_at=? "
        "WHERE id=? AND status IN ('queued', 'claimed', 'running')",
        (now, f"cancelled by {actor_id or 'user'}", now, int(task_id)),
    )
    if cur.rowcount <= 0:
        conn.commit()
        return get_agent_task(conn, int(task_id))
    record_agent_task_event(
        conn,
        int(task_id),
        "cancelled",
        actor_id=actor_id or "user",
        message=f"cancelled by {actor_id or 'user'}",
        now=now,
    )
    conn.commit()
    return get_agent_task(conn, int(task_id))
