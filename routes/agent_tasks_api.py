"""MyAgentWatch Agent Tasks v3 API."""

from __future__ import annotations

import json

from flask import jsonify, request

from myagentwatch.agent_tasks import (
    AGENT_ROLE_CAPABILITIES,
    ALL_CAPABILITIES,
    USER_ROLE_CAPABILITIES,
    approve_agent_task,
    cancel_agent_task,
    claim_agent_task,
    complete_agent_task,
    create_agent_task,
    fail_agent_task,
    get_agent_profile,
    get_agent_task,
    get_user_profile,
    list_agent_task_events,
    list_agent_tasks,
    recover_expired_agent_tasks,
    reject_agent_task,
    retry_agent_task,
    start_agent_task,
)
from myagentwatch.db import database
from myagentwatch.queries import query_chat_message_context


HIGH_RISK_CAPABILITIES = {
    "can_request_agent_task",
    "can_request_code_change",
    "can_request_shell_command",
    "can_autostart_agent",
    "can_manage_permissions",
}


def _actor_can_manage(conn, data: dict, target_kind: str, target_role: str, permissions: dict) -> tuple[bool, str]:
    actor_type = data.get("actor_type") or "user"
    actor_id = data.get("actor_id") or ""
    actor_name = data.get("actor_name") or "\u5929\u5b87"
    if actor_type == "agent":
        actor = get_agent_profile(conn, actor_id)
        if actor.get("role") != "agent-root":
            return False, "actor_agent_not_root"
        if target_role == "user-owner":
            return False, "agent_root_cannot_grant_user_owner"
        if target_role not in ("user-custom", "agent-custom"):
            return False, "agent_root_can_only_config_custom_roles"
        risky = [cap for cap, enabled in permissions.items() if enabled and cap in HIGH_RISK_CAPABILITIES]
        if risky:
            return False, "agent_root_cannot_grant_high_risk:" + ",".join(sorted(risky))
        return True, ""
    actor = get_user_profile(conn, actor_id, actor_name)
    if actor.get("role") == "user-owner":
        return True, ""
    return False, "actor_user_not_owner"


def register_agent_task_routes(app, socketio):
    @app.route("/api/permissions/roles", methods=["GET"])
    def api_permission_roles():
        return jsonify({
            "capabilities": list(ALL_CAPABILITIES),
            "user_roles": USER_ROLE_CAPABILITIES,
            "agent_roles": AGENT_ROLE_CAPABILITIES,
            "rules": {
                "user_owner_is_final_limit": True,
                "agent_root_can_config_custom_only": True,
                "agent_root_cannot_grant_user_owner": True,
            },
        })

    @app.route("/api/permissions/users/<path:user_id>", methods=["PATCH", "POST"])
    def api_permission_user_update(user_id):
        data = request.get_json(silent=True) or {}
        role = data.get("role") or "user-custom"
        if role not in USER_ROLE_CAPABILITIES:
            return jsonify({"error": "invalid_user_role"}), 400
        permissions = data.get("permissions") or {}
        if not isinstance(permissions, dict):
            return jsonify({"error": "invalid_permissions"}), 400
        with database() as conn:
            allowed, reason = _actor_can_manage(conn, data, "user", role, permissions)
            if not allowed:
                return jsonify({"error": "permission_denied", "reason": reason}), 403
            conn.execute(
                "UPDATE users SET role=?, permissions_json=? WHERE id=?",
                (role, json.dumps(permissions, ensure_ascii=False, sort_keys=True), user_id),
            )
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO users (id, name, type, role, permissions_json, created_at) "
                    "VALUES (?, ?, 'human', ?, ?, CAST(strftime('%s','now') AS INTEGER) * 1000)",
                    (user_id, data.get("name") or user_id, role, json.dumps(permissions, ensure_ascii=False, sort_keys=True)),
                )
            conn.commit()
            profile = get_user_profile(conn, user_id, data.get("name") or user_id)
        return jsonify({"user": profile})

    @app.route("/api/permissions/agents/<path:agent_id>", methods=["PATCH", "POST"])
    def api_permission_agent_update(agent_id):
        data = request.get_json(silent=True) or {}
        role = data.get("role") or "agent-custom"
        if role not in AGENT_ROLE_CAPABILITIES:
            return jsonify({"error": "invalid_agent_role"}), 400
        permissions = data.get("permissions") or {}
        if not isinstance(permissions, dict):
            return jsonify({"error": "invalid_permissions"}), 400
        with database() as conn:
            allowed, reason = _actor_can_manage(conn, data, "agent", role, permissions)
            if not allowed:
                return jsonify({"error": "permission_denied", "reason": reason}), 403
            conn.execute(
                "UPDATE agents SET role=?, permissions_json=? WHERE id=?",
                (role, json.dumps(permissions, ensure_ascii=False, sort_keys=True), agent_id),
            )
            conn.commit()
            profile = get_agent_profile(conn, agent_id)
        return jsonify({"agent": profile})

    @app.route("/api/agent/tasks", methods=["GET"])
    def api_agent_tasks():
        agent_id = request.args.get("agent_id") or None
        status = request.args.get("status") or None
        limit = min(request.args.get("limit", 50, type=int), 200)
        with database() as conn:
            tasks = list_agent_tasks(conn, agent_id=agent_id, status=status, limit=limit)
        return jsonify({"tasks": tasks})

    @app.route("/api/agent/tasks/<int:task_id>", methods=["GET"])
    def api_agent_task(task_id):
        with database() as conn:
            task = get_agent_task(conn, task_id)
            events = list_agent_task_events(conn, task_id) if task else []
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        task["events"] = events
        return jsonify({"task": task})

    @app.route("/api/agent/tasks/<int:task_id>/events", methods=["GET"])
    def api_agent_task_events(task_id):
        limit = min(request.args.get("limit", 200, type=int), 500)
        with database() as conn:
            task = get_agent_task(conn, task_id)
            if not task:
                return jsonify({"error": "task_not_found"}), 404
            events = list_agent_task_events(conn, task_id, limit=limit)
        return jsonify({"task_id": task_id, "events": events})

    @app.route("/api/agent/tasks/<int:task_id>/context", methods=["GET"])
    def api_agent_task_context(task_id):
        with database() as conn:
            task = get_agent_task(conn, task_id)
            if not task:
                return jsonify({"error": "task_not_found"}), 404
            events = list_agent_task_events(conn, task_id, limit=500)
            message_context = None
            if task.get("source_message_id"):
                message_context = query_chat_message_context(conn, int(task["source_message_id"]))
        task["events"] = events
        return jsonify({
            "task": task,
            "events": events,
            "message_context": message_context,
        })

    @app.route("/api/agent/tasks", methods=["POST"])
    def api_agent_task_create():
        data = request.get_json(silent=True) or {}
        agent_id = (data.get("agent_id") or "").strip()
        if not agent_id:
            return jsonify({"error": "agent_id_required"}), 400
        with database() as conn:
            task, denied = create_agent_task(
                conn,
                agent_id=agent_id,
                task_type=data.get("task_type") or "reply",
                title=data.get("title") or "",
                body=data.get("body") or data.get("content") or "",
                requester_id=data.get("requester_id") or "",
                requester_name=data.get("requester_name") or "\u5929\u5b87",
                requester_type=data.get("requester_type") or "user",
                source_conversation_id=data.get("source_conversation_id"),
                source_message_id=data.get("source_message_id"),
                source_title=data.get("source_title") or "",
                metadata=data.get("metadata") or {},
                priority=data.get("priority"),
            )
        if denied:
            return jsonify({"error": "permission_denied", "reason": denied}), 403
        socketio.emit("agent_task_update", {"task": task, "event": "created"})
        return jsonify({"task": task}), 201

    @app.route("/api/agent/tasks/<int:task_id>/cancel", methods=["POST"])
    def api_agent_task_cancel(task_id):
        data = request.get_json(silent=True) or {}
        with database() as conn:
            task = cancel_agent_task(conn, task_id, actor_id=data.get("actor_id") or "")
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        socketio.emit("agent_task_update", {"task": task, "event": "cancelled"})
        return jsonify({"task": task})

    @app.route("/api/agent/tasks/<int:task_id>/approve", methods=["POST"])
    def api_agent_task_approve(task_id):
        data = request.get_json(silent=True) or {}
        with database() as conn:
            task = approve_agent_task(
                conn,
                task_id,
                actor_id=data.get("actor_id") or "tianyu",
                actor_name=data.get("actor_name") or "\u5929\u5b87",
            )
            events = list_agent_task_events(conn, task_id) if task else []
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        task["events"] = events
        socketio.emit("agent_task_update", {"task": task, "event": "approved"})
        return jsonify({"task": task, "events": events})

    @app.route("/api/agent/tasks/<int:task_id>/reject", methods=["POST"])
    def api_agent_task_reject(task_id):
        data = request.get_json(silent=True) or {}
        with database() as conn:
            task = reject_agent_task(
                conn,
                task_id,
                actor_id=data.get("actor_id") or "tianyu",
                actor_name=data.get("actor_name") or "\u5929\u5b87",
                reason=data.get("reason") or data.get("rejected_reason") or "",
            )
            events = list_agent_task_events(conn, task_id) if task else []
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        task["events"] = events
        socketio.emit("agent_task_update", {"task": task, "event": "rejected"})
        return jsonify({"task": task, "events": events})

    @app.route("/api/agent/tasks/<int:task_id>/retry", methods=["POST"])
    def api_agent_task_retry(task_id):
        data = request.get_json(silent=True) or {}
        with database() as conn:
            task = retry_agent_task(
                conn,
                task_id,
                actor_id=data.get("actor_id") or "tianyu",
                actor_name=data.get("actor_name") or "\u5929\u5b87",
            )
            events = list_agent_task_events(conn, task_id) if task else []
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        task["events"] = events
        socketio.emit("agent_task_update", {"task": task, "event": "retried"})
        return jsonify({"task": task, "events": events})

    @app.route("/api/daemon/tasks/claim", methods=["POST"])
    def api_daemon_task_claim():
        data = request.get_json(silent=True) or {}
        agent_id = (data.get("agent_id") or "").strip()
        if not agent_id:
            return jsonify({"error": "agent_id_required"}), 400
        allowed = data.get("allowed_task_types") or []
        if isinstance(allowed, str):
            allowed = [item.strip() for item in allowed.split(",") if item.strip()]
        with database() as conn:
            task = claim_agent_task(
                conn,
                agent_id=agent_id,
                claimed_by=data.get("claimed_by") or "myaw-daemon",
                task_id=data.get("task_id"),
                allowed_task_types=allowed,
                lease_seconds=data.get("lease_seconds") or 300,
            )
        if not task:
            return jsonify({"task": None})
        socketio.emit("agent_task_update", {"task": task, "event": "claimed"})
        return jsonify({"task": task})

    @app.route("/api/daemon/tasks/<int:task_id>/start", methods=["POST"])
    def api_daemon_task_start(task_id):
        data = request.get_json(silent=True) or {}
        with database() as conn:
            task = start_agent_task(conn, task_id, actor_id=data.get("actor_id") or "")
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        socketio.emit("agent_task_update", {"task": task, "event": "started"})
        return jsonify({"task": task})

    @app.route("/api/daemon/tasks/recover-expired", methods=["POST"])
    def api_daemon_task_recover_expired():
        with database() as conn:
            recovered = recover_expired_agent_tasks(conn)
        if recovered:
            socketio.emit("agent_task_update", {"event": "recovered", "count": recovered})
        return jsonify({"recovered": recovered})

    @app.route("/api/daemon/tasks/<int:task_id>/complete", methods=["POST"])
    def api_daemon_task_complete(task_id):
        data = request.get_json(silent=True) or {}
        result = data.get("result_text") or data.get("output") or ""
        with database() as conn:
            task = complete_agent_task(conn, task_id, result, metadata=data.get("metadata") or {})
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        socketio.emit("agent_task_update", {"task": task, "event": "completed"})
        return jsonify({"task": task})

    @app.route("/api/daemon/tasks/<int:task_id>/fail", methods=["POST"])
    def api_daemon_task_fail(task_id):
        data = request.get_json(silent=True) or {}
        with database() as conn:
            task = fail_agent_task(conn, task_id, data.get("error_text") or data.get("error") or "")
        if not task:
            return jsonify({"error": "task_not_found"}), 404
        socketio.emit("agent_task_update", {"task": task, "event": "failed"})
        return jsonify({"task": task})
