"""MyAgentWatch API Routes — all REST endpoints."""

import time as _time
import json as _json
from myagentwatch.db import database as _get_database

_heartbeat_buffer: dict[str, dict] = {}
_socketio = None


def _create_inbox_item(recipient_id="\u5929\u5b87", recipient_type="human",
                        item_type="system", severity="info",
                        title="", body="", link="", source_agent="",
                        source_conversation_id=None, source_message_id=None,
                        delivery_type="", source_title="", metadata=None):
    now = int(_time.time() * 1000)
    metadata_json = _json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    with _get_database() as conn:
        conn.execute(
            "INSERT INTO inbox (recipient_type, recipient_id, type, severity, "
            "title, body, link, source_agent_id, source_conversation_id, "
            "source_message_id, delivery_type, source_title, metadata_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (recipient_type, recipient_id, item_type, severity,
             title, body, link, source_agent, source_conversation_id,
             source_message_id, delivery_type, source_title, metadata_json, now),
        )
        conn.commit()
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if _socketio:
        _socketio.emit("inbox_update", {
            "id": item_id, "title": title, "body": body,
            "severity": severity, "type": item_type,
            "source_agent": source_agent, "source_conversation_id": source_conversation_id,
            "source_message_id": source_message_id, "delivery_type": delivery_type,
            "source_title": source_title, "timestamp": now,
        })
    return item_id


def _heartbeat_agent_identity(agent_id: str, hb: dict) -> dict:
    parts = agent_id.split(":")
    provider_id = parts[0] if len(parts) > 1 else ""
    name = parts[1] if len(parts) >= 3 else (parts[-1] if parts else agent_id)
    model_id = hb.get("model_id") or (parts[2] if len(parts) >= 3 else "")
    if provider_id == "myagentwatch-cli":
        group_name = model_id or name
        return {
            "name": name,
            "display_name": name,
            "group_name": group_name,
            "agent_type": group_name,
            "model_id": model_id,
            "provider_id": group_name,
        }
    return {
        "name": name,
        "display_name": name,
        "group_name": provider_id or "",
        "agent_type": provider_id or "",
        "model_id": model_id,
        "provider_id": provider_id or "",
    }


def flush_heartbeats():
    if not _heartbeat_buffer:
        return
    batch = dict(_heartbeat_buffer)
    _heartbeat_buffer.clear()
    now_ms = int(_time.time() * 1000)
    with _get_database() as conn:
        for agent_id, hb in batch.items():
            reported_status = hb.get("status", "active")
            metadata_json = _json.dumps(hb.get("metadata", {}), ensure_ascii=False)
            auth_user = hb.get("auth_user") or ""
            model_id = hb.get("model_id", "")
            conn.execute(
                """UPDATE agents SET
                   last_heartbeat_at = ?,
                   updated_at = ?,
                   status = ?,
                   status_since = CASE WHEN status != ? THEN ? ELSE status_since END,
                   model_id = CASE WHEN ? != '' THEN ? ELSE model_id END,
                   metadata = json_set(
                     COALESCE(metadata, '{}'),
                     '$.heartbeat_status', ?,
                     '$.heartbeat_metadata', ?,
                     '$.heartbeat_auth_user', ?
                   )
                   WHERE id = ?""",
                (
                    hb["last_heartbeat_at"],
                    now_ms,
                    reported_status,
                    reported_status,
                    now_ms,
                    model_id,
                    model_id,
                    reported_status,
                    metadata_json,
                    auth_user,
                    agent_id,
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                ident = _heartbeat_agent_identity(agent_id, hb)
                conn.execute(
                    "INSERT OR IGNORE INTO agents (id, name, display_name, group_name, "
                    "agent_type, model_id, provider_id, status, "
                    "last_heartbeat_at, last_seen_time, status_since, metadata, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        agent_id,
                        ident["name"],
                        ident["display_name"],
                        ident["group_name"],
                        ident["agent_type"],
                        ident["model_id"],
                        ident["provider_id"],
                        reported_status,
                        hb["last_heartbeat_at"],
                        hb["last_heartbeat_at"],
                        now_ms,
                        _json.dumps(
                            {
                                "heartbeat_status": reported_status,
                                "heartbeat_metadata": hb.get("metadata", {}),
                                "heartbeat_auth_user": auth_user,
                            },
                            ensure_ascii=False,
                        ),
                        now_ms,
                        now_ms,
                    ),
                )
        conn.commit()


def register_api_routes(app, collector, config, socketio):
    global _socketio
    _socketio = socketio

    import os
    import time

    import psutil
    from flask import jsonify, request

    from myagentwatch.db import database
    from myagentwatch.queries import (
        query_all_agents,
        query_chart_data,
        query_overview_cards,
        query_sessions,
        query_turn_counts_by_agent,
        query_turn_detail,
        query_turn_tree,
        query_turns,
        query_turn_trace,
    )

    START_TIME = app.config.get("START_TIME", time.time())

    def _fmt_uptime(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h}h {m}m {s}s"

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    @app.route("/api/status")
    def api_status():
        return jsonify(
            {
                "status": "ok",
                "version": "2.0.0",
                "uptime": _fmt_uptime(time.time() - START_TIME),
                "uptime_seconds": round(time.time() - START_TIME, 1),
                "poll_interval": config.get("poll_interval", 2),
            }
        )

    @app.route("/api/agents")
    def api_agents():
        with database() as conn:
            agents = query_all_agents(conn)
        return jsonify({"agents": agents, "total": len(agents)})

    @app.route("/api/sessions")
    def api_sessions():
        with database() as conn:
            sessions = query_sessions(conn)
        return jsonify({"sessions": sessions, "total": len(sessions)})

    # ── Task Lifecycle ──

    @app.route("/api/tasks")
    def api_tasks():
        status = request.args.get("status")
        assigned_agent_id = request.args.get("agent_id")
        limit = min(request.args.get("limit", 100, type=int), 500)
        with database() as conn:
            from myagentwatch.tasks import auto_track_tasks, list_tasks

            changed = auto_track_tasks(
                conn,
                heartbeat_timeout_sec=config.get("heartbeat_timeout", 300),
            )
            if changed:
                conn.commit()
            tasks = list_tasks(conn, status=status, assigned_agent_id=assigned_agent_id, limit=limit)
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
            ).fetchall()
            counts = {r["status"]: r["cnt"] for r in rows}
        for task in changed:
            socketio.emit("task_update", {"type": "auto_status", "task": task})
        return jsonify({"tasks": tasks, "counts": counts, "total": len(tasks)})

    @app.route("/api/tasks", methods=["POST"])
    def api_tasks_create():
        data = request.get_json(silent=True) or {}
        try:
            with database() as conn:
                from myagentwatch.tasks import create_task

                task = create_task(
                    conn,
                    title=data.get("title", ""),
                    description=data.get("description", ""),
                    status=data.get("status", "queued"),
                    assigned_agent_id=data.get("assigned_agent_id", ""),
                    parent_task_id=data.get("parent_task_id"),
                    session_id=data.get("session_id", ""),
                    priority=data.get("priority", 0),
                    tags=data.get("tags", []),
                    metadata=data.get("metadata", {}),
                    actor_id=data.get("actor_id", "天宇"),
                )
                conn.commit()
            socketio.emit("task_update", {"type": "created", "task": task})
            return jsonify({"task": task}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/tasks/<int:task_id>")
    def api_task_detail(task_id):
        with database() as conn:
            from myagentwatch.tasks import auto_track_tasks, get_task, task_timeline

            changed = auto_track_tasks(
                conn,
                heartbeat_timeout_sec=config.get("heartbeat_timeout", 300),
            )
            if changed:
                conn.commit()
            task = get_task(conn, task_id)
            if not task:
                return jsonify({"error": "task not found"}), 404
            timeline = task_timeline(conn, task_id)
        for task_item in changed:
            socketio.emit("task_update", {"type": "auto_status", "task": task_item})
        return jsonify({"task": task, "timeline": timeline})

    @app.route("/api/tasks/<int:task_id>/timeline")
    def api_task_timeline(task_id):
        with database() as conn:
            from myagentwatch.tasks import get_task, task_timeline

            if not get_task(conn, task_id):
                return jsonify({"error": "task not found"}), 404
            timeline = task_timeline(conn, task_id)
        return jsonify({"timeline": timeline, "task_id": task_id})

    @app.route("/api/tasks/<int:task_id>/status", methods=["PATCH", "POST"])
    def api_task_status(task_id):
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        if not status:
            return jsonify({"error": "status required"}), 400
        try:
            with database() as conn:
                from myagentwatch.tasks import update_task_status

                task = update_task_status(
                    conn,
                    task_id,
                    status,
                    actor_id=data.get("actor_id", "天宇"),
                    message=data.get("message", ""),
                    metadata=data.get("metadata", {}),
                )
                conn.commit()
            socketio.emit("task_update", {"type": "status", "task": task})
            return jsonify({"task": task})
        except LookupError:
            return jsonify({"error": "task not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/stats/overview")
    def api_stats_overview():
        with database() as conn:
            result = query_overview_cards(conn)
        return jsonify(result)

    @app.route("/api/health")
    def api_health():
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        source_health = collector.get_health()
        return jsonify(
            {
                "cpu_pct": cpu,
                "memory_mb": round(mem.used / (1024 * 1024), 1),
                "memory_pct": mem.percent,
                "disk_pct": disk.percent,
                "uptime_seconds": round(time.time() - START_TIME, 1),
                "uptime_display": _fmt_uptime(time.time() - START_TIME),
                "sources": source_health,
            }
        )

    @app.route("/api/timeline")
    def api_timeline():
        with database() as conn:
            rows = conn.execute(
                "SELECT id, session_id, agent_id, event_type, severity, timestamp "
                "FROM activity_log ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
            entries = [dict(r) for r in rows]
        return jsonify({"entries": entries, "total": len(entries)})

    @app.route("/api/stats/tokens")
    def api_stats_tokens():
        with database() as conn:
            rows = conn.execute(
                "SELECT agent_id, SUM(tokens_input) as inp, SUM(tokens_output) as outp, "
                "SUM(tokens_reasoning) as reas, SUM(cache_read) as cache_r, "
                "SUM(cache_write) as cache_w, SUM(cost) as cost "
                "FROM token_records GROUP BY agent_id"
            ).fetchall()
        return jsonify({"stats": [dict(r) for r in rows]})

    @app.route("/api/stats/charts")
    def api_stats_charts():
        with database() as conn:
            result = query_chart_data(conn)
        return jsonify(result)

    @app.route("/api/sessions/<session_id>")
    def api_session_detail(session_id):
        with database() as conn:
            session = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                return jsonify({"error": "Session not found"}), 404

            msgs = conn.execute(
                "SELECT id, agent_id, message_id as msg_id, part_id, model_id, "
                "tokens_input, tokens_output, tokens_reasoning, cost, timestamp "
                "FROM token_records WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            tools = conn.execute(
                "SELECT * FROM tool_calls WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            activities = conn.execute(
                "SELECT * FROM activity_log WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
        return jsonify(
            {
                "session": dict(session),
                "messages": [dict(m) for m in msgs],
                "tool_calls": [dict(t) for t in tools],
                "activities": [dict(a) for a in activities],
            }
        )

    @app.route("/api/timeline/flow/<session_id>")
    def api_timeline_flow_session(session_id):
        with database() as conn:
            activities = conn.execute(
                "SELECT id, event_type, data, timestamp FROM activity_log "
                "WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
            tools = conn.execute(
                "SELECT id, part_id, tool_name, call_id, status, description, "
                "exit_code, duration_ms, timestamp FROM tool_calls "
                "WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()

        tool_by_ts = {}
        for t in tools:
            key = t["timestamp"] // 100
            if key not in tool_by_ts:
                tool_by_ts[key] = []
            tool_by_ts[key].append(t)

        nodes, edges = [], []
        prev_id = None
        for act in activities:
            nid = f"act_{act['id']}"
            label = act["event_type"].replace("part_", "")
            tool = None
            status = None
            desc = None
            ts_key = act["timestamp"] // 100
            if ts_key in tool_by_ts and tool_by_ts[ts_key]:
                matched = tool_by_ts[ts_key].pop(0)
                label = matched["tool_name"] or label
                tool = matched["tool_name"]
                status = matched["status"]
                desc = matched["description"]
            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "tool": tool,
                    "status": status,
                    "description": desc,
                }
            )
            if prev_id:
                edges.append({"from": prev_id, "to": nid})
            prev_id = nid
        return jsonify({"nodes": nodes, "edges": edges})

    @app.route("/api/timeline/flow")
    def api_timeline_flow():
        since = int((time.time() - 3600) * 1000)
        with database() as conn:
            parts = conn.execute(
                "SELECT al.id, al.session_id, al.agent_id, al.event_type, al.timestamp, "
                "tc.tool_name, tc.call_id, tc.status as tool_status, tc.description, "
                "tc.exit_code, tc.duration_ms "
                "FROM activity_log al "
                "LEFT JOIN tool_calls tc ON tc.session_id = al.session_id "
                "AND tc.timestamp BETWEEN al.timestamp - 500 AND al.timestamp + 500 "
                "AND tc.tool_name IS NOT NULL "
                "WHERE al.timestamp >= ? AND al.event_type LIKE 'part_%' "
                "ORDER BY al.timestamp DESC LIMIT 200",
                (since,),
            ).fetchall()

        nodes, edges = [], []
        node_ids = set()
        for i, p in enumerate(parts):
            nid = str(p["id"])
            if nid in node_ids:
                continue
            node_ids.add(nid)
            label = p["event_type"].replace("part_", "")
            if p["tool_name"]:
                label = p["tool_name"]
            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "tool": p["tool_name"],
                    "status": p["tool_status"],
                    "description": p["description"],
                    "session": p["session_id"],
                }
            )
            if i > 0:
                edges.append({"from": str(parts[i - 1]["id"]), "to": nid})
        return jsonify({"nodes": nodes, "edges": edges})

    @app.route("/api/alerts")
    def api_alerts():
        with database() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        return jsonify({"alerts": [dict(r) for r in rows]})

    @app.route("/api/alerts/resolve", methods=["POST"])
    def api_alerts_resolve():
        alert_id = request.json.get("id") if request.is_json else request.args.get("id")
        with database() as conn:
            conn.execute(
                "UPDATE alerts SET is_active = 0, resolved_at = ? WHERE id = ?",
                (int(time.time() * 1000), alert_id),
            )
            conn.commit()
        return jsonify({"status": "ok"})

    @app.route("/api/logs/live")
    def api_logs_live():
        all_lines = []
        for name, source in collector.sources.items():
            if hasattr(source, "get_recent_lines"):
                lines = source.get_recent_lines(count=100)
                for line in lines:
                    line["source"] = name
                all_lines.extend(lines)
        all_lines.sort(key=lambda x: x.get("timestamp", ""))
        return jsonify({"lines": all_lines[-200:], "total": len(all_lines)})

    # SSE streams
    @app.route("/api/events/stream")
    def api_events_stream():
        from flask import Response

        from myagentwatch.event_bus import event_bus

        return Response(
            event_bus.sse_stream("activity"),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/api/logs/stream")
    def api_logs_stream():
        from flask import Response

        from myagentwatch.event_bus import event_bus

        return Response(
            event_bus.sse_stream("log"),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Config management
    @app.route("/api/config/template", methods=["POST"])
    def api_config_template():
        try:
            data = request.get_json(force=True)
            template_name = data.get("template", "default")
            from myagentwatch.templates.template_engine import (
                apply_template,
            )

            merged = apply_template({"template": template_name, **config})
            return jsonify(
                {
                    "status": "ok",
                    "template": template_name,
                    "agent_meta": merged.get("agent_meta", {}),
                    "message": f"Template '{template_name}' applied. Restart to take full effect.",
                }
            )
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400

    @app.route("/api/config/templates")
    def api_config_templates():
        from myagentwatch.templates.template_engine import list_templates

        templates = list_templates()
        return jsonify(
            {
                "active": config.get("template", "default"),
                "templates": templates,
            }
        )

    # ── Token Dashboard ──

    @app.route("/api/tokens/dashboard")
    def api_tokens_dashboard():
        days = request.args.get("days", 7, type=int)
        agent_id = request.args.get("agent_id")
        model_id = request.args.get("model_id")
        with database() as conn:
            from myagentwatch.queries import query_token_by_day, query_token_by_model

            by_day = query_token_by_day(conn, days, agent_id, model_id)
            by_model = query_token_by_model(conn, days, agent_id)
        return jsonify({"by_day": by_day, "by_model": by_model, "days": days})

    @app.route("/api/tokens/by-hour")
    def api_tokens_by_hour():
        date_str = request.args.get("date", time.strftime("%Y-%m-%d"))
        agent_id = request.args.get("agent_id")
        with database() as conn:
            from myagentwatch.queries import query_token_by_hour

            hours = query_token_by_hour(conn, date_str, agent_id)
        return jsonify({"hours": hours, "date": date_str})

    @app.route("/api/tokens/by-model")
    def api_tokens_by_model():
        days = request.args.get("days", 30, type=int)
        with database() as conn:
            from myagentwatch.queries import query_token_by_model

            models = query_token_by_model(conn, days)
        return jsonify({"models": models, "days": days})

    # ── User & PAT ──

    @app.route("/api/users")
    def api_users():
        from myagentwatch.user import list_users
        with database() as conn:
            users = list_users(conn)
        return jsonify({"users": users})

    @app.route("/api/users/<user_id>/token", methods=["POST"])
    def api_issue_token(user_id):
        from myagentwatch.user import issue_pat_for
        with database() as conn:
            token = issue_pat_for(conn, user_id)
        if not token:
            return jsonify({"error": "user not found"}), 404
        return jsonify({"token": token, "user_id": user_id})

    @app.route("/api/users/<user_id>/token", methods=["DELETE"])
    def api_revoke_token(user_id):
        with database() as conn:
            conn.execute(
                "UPDATE users SET token_hash = NULL, token_prefix = NULL, token_created_at = NULL WHERE id = ?",
                (user_id,),
            )
            conn.commit()
        return jsonify({"status": "ok"})

    def _verify_agent_token():
        """Check Authorization header for valid agent PAT. Returns user dict or None."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:]
        with database() as conn:
            from myagentwatch.user import verify_token
            return verify_token(conn, token)

    def _optional_auth_user():
        if not request.headers.get("Authorization"):
            return None
        user = _verify_agent_token()
        if not user:
            return False
        return user

    def _num(value, default=None):
        if value in (None, ""):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _int_or_none(value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _ingest_agent_id(body, auth_user):
        agent_id = (body.get("agent_id") or "").strip()
        if not agent_id and isinstance(auth_user, dict):
            agent_id = auth_user.get("id", "")
        return agent_id

    # ── Agent ingest endpoints (CLI-side monitoring reports) ──

    @app.route("/api/agent-ingest/resources", methods=["POST"])
    def api_agent_ingest_resources():
        body = request.get_json(silent=True) or {}
        auth_user = _optional_auth_user()
        if auth_user is False:
            return jsonify({"error": "invalid token"}), 401

        agent_id = _ingest_agent_id(body, auth_user)
        if not agent_id:
            return jsonify({"error": "agent_id required"}), 400
        timestamp = _int_or_none(body.get("timestamp")) or int(time.time() * 1000)

        with database() as conn:
            cur = conn.execute(
                """INSERT INTO agent_resources
                   (agent_id, cpu_pct, memory_pct, memory_used_mb, memory_total_mb,
                    disk_pct, disk_used_gb, disk_total_gb, gpu_pct,
                    gpu_memory_used_mb, net_sent_bytes, net_recv_bytes, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    _num(body.get("cpu_pct")),
                    _num(body.get("memory_pct")),
                    _num(body.get("memory_used_mb")),
                    _num(body.get("memory_total_mb")),
                    _num(body.get("disk_pct")),
                    _num(body.get("disk_used_gb")),
                    _num(body.get("disk_total_gb")),
                    _num(body.get("gpu_pct")),
                    _num(body.get("gpu_memory_used_mb")),
                    _int_or_none(body.get("net_sent_bytes")),
                    _int_or_none(body.get("net_recv_bytes")),
                    timestamp,
                ),
            )
            conn.commit()
            row_id = cur.lastrowid
        return jsonify({"ok": True, "id": row_id, "agent_id": agent_id}), 201

    @app.route("/api/agent-ingest/processes", methods=["POST"])
    def api_agent_ingest_processes():
        body = request.get_json(silent=True) or {}
        auth_user = _optional_auth_user()
        if auth_user is False:
            return jsonify({"error": "invalid token"}), 401

        agent_id = _ingest_agent_id(body, auth_user)
        if not agent_id:
            return jsonify({"error": "agent_id required"}), 400
        timestamp = _int_or_none(body.get("timestamp")) or int(time.time() * 1000)
        processes = body.get("processes")
        if processes is None:
            processes = [body.get("process", body)]
        if not isinstance(processes, list):
            return jsonify({"error": "processes must be a list"}), 400

        ids = []
        with database() as conn:
            for proc in processes[:200]:
                if not isinstance(proc, dict):
                    continue
                name = str(proc.get("process_name") or proc.get("name") or "").strip()
                if not name:
                    continue
                cur = conn.execute(
                    """INSERT INTO agent_processes
                       (agent_id, pid, process_name, cmdline, status,
                        cpu_pct, memory_mb, detected_role, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        agent_id,
                        _int_or_none(proc.get("pid")),
                        name,
                        str(proc.get("cmdline") or ""),
                        str(proc.get("status") or ""),
                        _num(proc.get("cpu_pct")),
                        _num(proc.get("memory_mb")),
                        str(proc.get("detected_role") or ""),
                        _int_or_none(proc.get("timestamp")) or timestamp,
                    ),
                )
                ids.append(cur.lastrowid)
            conn.commit()
        return jsonify({
            "ok": True,
            "id": ids[0] if ids else None,
            "ids": ids,
            "count": len(ids),
            "agent_id": agent_id,
        }), 201

    # ── Inbox ──

    @app.route("/api/inbox")
    def api_inbox():
        recipient = request.args.get("recipient", "天宇")
        limit = min(request.args.get("limit", 50, type=int), 200)
        with database() as conn:
            rows = conn.execute(
                "SELECT * FROM inbox WHERE is_archived = 0 "
                "AND (recipient_id = ? OR recipient_id = '') "
                "ORDER BY created_at DESC LIMIT ?",
                (recipient, limit),
            ).fetchall()
            unread = conn.execute(
                "SELECT COUNT(*) as cnt FROM inbox "
                "WHERE is_read = 0 AND is_archived = 0 "
                "AND (recipient_id = ? OR recipient_id = '')",
                (recipient,),
            ).fetchone()["cnt"]
        return jsonify({"items": [dict(r) for r in rows], "unread": unread})

    @app.route("/api/inbox/read/<int:item_id>", methods=["POST"])
    def api_inbox_read(item_id):
        with database() as conn:
            conn.execute(
                "UPDATE inbox SET is_read = 1 WHERE id = ?", (item_id,)
            )
            conn.commit()
        return jsonify({"status": "ok"})

    @app.route("/api/inbox/read-all", methods=["POST"])
    def api_inbox_read_all():
        recipient = request.args.get("recipient", "天宇")
        with database() as conn:
            conn.execute(
                "UPDATE inbox SET is_read = 1 "
                "WHERE is_read = 0 AND (recipient_id = ? OR recipient_id = '')",
                (recipient,),
            )
            conn.commit()
        return jsonify({"status": "ok"})

    @app.route("/api/inbox/archive/<int:item_id>", methods=["POST"])
    def api_inbox_archive(item_id):
        with database() as conn:
            conn.execute(
                "UPDATE inbox SET is_archived = 1 WHERE id = ?", (item_id,)
            )
            conn.commit()
        return jsonify({"status": "ok"})

    # ── Pricing Management ──

    @app.route("/api/tokens/by-agent")
    def api_tokens_by_agent():
        days = request.args.get("days", 30, type=int)
        with database() as conn:
            from myagentwatch.queries import query_token_by_agent
            rows = query_token_by_agent(conn, days)
        return jsonify({"agents": rows, "days": days})

    @app.route("/api/tokens/unmapped")
    def api_tokens_unmapped():
        with database() as conn:
            from myagentwatch.queries import query_unmapped_models
            unmapped = query_unmapped_models(conn)
        return jsonify({"unmapped": unmapped, "count": len(unmapped)})

    @app.route("/api/pricing")
    def api_pricing_list():
        with database() as conn:
            from myagentwatch.pricing import load_pricing

            table = load_pricing(conn)
            rows = conn.execute(
                "SELECT * FROM pricing WHERE is_active = 1 ORDER BY provider_id, model_id"
            ).fetchall()
        return jsonify({"pricing": [dict(r) for r in rows], "table": table})

    @app.route("/api/pricing", methods=["POST"])
    def api_pricing_add():
        data = request.get_json(silent=True) or {}
        required = ["provider_id", "model_id", "display_name",
                     "price_per_1m_input", "price_per_1m_output"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400
        now_ms = int(time.time() * 1000)
        with database() as conn:
            try:
                conn.execute(
                    "INSERT INTO pricing (provider_id, model_id, display_name, "
                    "price_per_1m_input, price_per_1m_output, "
                    "price_per_1m_cache_read, price_per_1m_cache_write, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        data["provider_id"], data["model_id"], data["display_name"],
                        data["price_per_1m_input"], data["price_per_1m_output"],
                        data.get("price_per_1m_cache_read", 0),
                        data.get("price_per_1m_cache_write", 0),
                        now_ms,
                    ),
                )
                conn.commit()
                return jsonify({"status": "ok", "id": conn.execute("SELECT last_insert_rowid()").fetchone()[0]})
            except Exception as e:
                return jsonify({"error": str(e)}), 409

    @app.route("/api/pricing/<int:price_id>", methods=["DELETE"])
    def api_pricing_delete(price_id):
        with database() as conn:
            conn.execute(
                "UPDATE pricing SET is_active = 0 WHERE id = ?", (price_id,)
            )
            conn.commit()
        return jsonify({"status": "ok"})

    # ── Heartbeat endpoint (uses module-level _heartbeat_buffer) ──

    VALID_AGENT_STATUSES = {"active", "working", "idle", "blocked", "error", "offline"}

    @app.route("/api/heartbeat/<agent_id>", methods=["POST"])
    def api_heartbeat(agent_id):
        if not agent_id or len(agent_id.strip()) < 2:
            return jsonify({"error": "invalid agent_id"}), 400
        agent_id = agent_id.strip()
        now_ms = int(time.time() * 1000)
        body = request.get_json(silent=True) or {}
        reported_status = body.get("status", "active")
        if reported_status not in VALID_AGENT_STATUSES:
            return jsonify({"error": f"invalid status: {reported_status}"}), 400
        metadata = body.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        model_id = (body.get("model_id") or "").strip()

        # Optional PAT verification — records which agent sent the heartbeat
        auth_user = _verify_agent_token() if request.headers.get("Authorization") else None
        _heartbeat_buffer[agent_id] = {
            "last_heartbeat_at": now_ms,
            "status": reported_status,
            "metadata": metadata,
            "model_id": model_id,
            "auth_user": auth_user["id"] if auth_user else None,
        }
        return jsonify({"status": "ok", "agent_status": reported_status})

    # ── SocketIO event handlers ──
    @socketio.on("connect")
    def handle_connect():
        import logging
        from routes.ws import build_snapshot

        logging.getLogger("myagentwatch").info("WebSocket client connected")
        snapshot = build_snapshot()
        if snapshot:
            from flask_socketio import emit
            emit("stat_snapshot", snapshot)

    @socketio.on("disconnect")
    def handle_disconnect():
        import logging

        logging.getLogger("myagentwatch").info("WebSocket client disconnected")

    @socketio.on("subscribe_logs")
    def handle_subscribe_logs(data):
        import logging

        logging.getLogger("myagentwatch").info(f"Log subscription: {data}")

    @socketio.on("subscribe_agent")
    def handle_subscribe_agent(data):
        from flask_socketio import join_room

        agent_id = data.get("agent_id") if isinstance(data, dict) else str(data)
        if agent_id:
            join_room(f"agent:{agent_id}")

    @socketio.on("unsubscribe_agent")
    def handle_unsubscribe_agent(data):
        from flask_socketio import leave_room

        agent_id = data.get("agent_id") if isinstance(data, dict) else str(data)
        if agent_id:
            leave_room(f"agent:{agent_id}")

    @socketio.on("chat_message")
    def handle_chat_message(data):
        import logging
        logger = logging.getLogger("myagentwatch")
        msg = data.get("message", "") if isinstance(data, dict) else str(data)
        sender = data.get("sender", "未知 Agent") if isinstance(data, dict) else "未知 Agent"
        logger.info(f"Chat broadcast: [{sender}] {msg}")
        # Broadcast to all connected clients
        socketio.emit("chat_message", {
            "message": msg,
            "sender": sender,
            "timestamp": int(time.time() * 1000),
        })

    # ── 对话日志 API ──

    @app.route("/api/logs/turns")
    def api_logs_turns():
        agent_id = request.args.get("agent")
        phase = request.args.get("phase")
        severity = request.args.get("severity")
        search = request.args.get("q")
        trace_id = request.args.get("trace")
        since = request.args.get("since", type=int)
        until = request.args.get("until", type=int)
        limit = min(request.args.get("limit", 200, type=int), 1000)
        offset = request.args.get("offset", 0, type=int)

        with database() as conn:
            from myagentwatch.queries import query_turns

            turns, total = query_turns(
                conn,
                agent_id=agent_id,
                phase=phase,
                severity=severity,
                search=search,
                trace_id=trace_id,
                since=since,
                until=until,
                limit=limit,
                offset=offset,
            )
        return jsonify({"turns": turns, "total": total})

    @app.route("/api/logs/tree")
    def api_logs_tree():
        with database() as conn:
            from myagentwatch.queries import query_turn_tree

            tree = query_turn_tree(conn)
        return jsonify({"tree": tree})

    @app.route("/api/logs/turn/<int:turn_id>")
    def api_logs_turn_detail(turn_id):
        with database() as conn:
            from myagentwatch.queries import query_turn_detail

            detail = query_turn_detail(conn, turn_id)
        if not detail:
            return jsonify({"error": "Turn not found"}), 404
        return jsonify(detail)

    @app.route("/api/logs/trace/<trace_id>")
    def api_logs_trace(trace_id):
        with database() as conn:
            from myagentwatch.queries import query_turn_trace

            data = query_turn_trace(conn, trace_id)
        return jsonify(data)

    @app.route("/api/logs/export")
    def api_logs_export():
        fmt = request.args.get("format", "json")
        agent_id = request.args.get("agent")
        since = request.args.get("since", type=int)
        until = request.args.get("until", type=int)

        with database() as conn:
            from myagentwatch.queries import query_turns

            turns, total = query_turns(
                conn, agent_id=agent_id, since=since, until=until, limit=5000
            )

        if fmt == "markdown":
            from myagentwatch.log_compiler import turns_to_markdown

            md = turns_to_markdown(turns)
            return md, 200, {"Content-Type": "text/markdown; charset=utf-8"}

        return jsonify({"turns": turns, "total": total})
