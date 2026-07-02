"""Data collection scheduler and orchestrator.

Uses the source registry (sources/__init__.py) to discover and instantiate
data source adapters. Any tool registered via @register_source can be added
in config.yaml with a single line — no collector code changes needed.
"""

import logging
import time

from myagentwatch.db import database
from myagentwatch.sources import SOURCE_REGISTRY
from myagentwatch.sources.base import CollectedData, SourceInterface
from myagentwatch.sources.log_adapter import LogAdapter
from myagentwatch.sources.system import SystemSource

logger = logging.getLogger("myagentwatch.collector")


class Collector:
    """Orchestrates data collection from all configured sources."""

    def __init__(self, config: dict):
        self.config = config
        self.sources: dict[str, SourceInterface] = {}
        self.source_types: dict[str, str] = {}
        self.last_sync: dict[str, int] = {}
        self.source_healthy: dict[str, bool] = {}
        self._init_sources()

    def _init_sources(self):
        from myagentwatch.sources.opencode_log import OpenCodeLogSource

        for ds_cfg in self.config.get("data_sources", []):
            if not ds_cfg.get("enabled", True):
                continue
            name = ds_cfg["name"]
            source_type = ds_cfg["type"]

            SourceCls = SOURCE_REGISTRY.get(source_type)
            if SourceCls is None:
                logger.warning(
                    f"Unknown source type '{source_type}' for '{name}'. "
                    f"Available: {list(SOURCE_REGISTRY.keys())}"
                )
                continue

            source_kwargs = {
                k: v for k, v in ds_cfg.items() if k not in ("name", "type", "enabled")
            }
            source = SourceCls(name=name, **source_kwargs)
            if source.connect():
                self.sources[name] = source
                self.source_types[name] = source_type
                self.last_sync[name] = 0
                logger.info(f"Source '{name}' connected (type={source_type})")

            # Auto-create log-file sidecar if log_dir is present
            log_dir = ds_cfg.get("log_dir", "")
            if log_dir:
                log_name = f"{name}-logs"
                log_src = OpenCodeLogSource(name=log_name, log_dir=log_dir)
                if log_src.connect():
                    self.sources[log_name] = log_src
                    self.source_types[log_name] = "opencode_log"
                    self.last_sync[log_name] = 0
                    logger.info(f"Log source '{log_name}' connected")

        # Always add system source
        sys_src = SystemSource()
        if sys_src.connect():
            self.sources["system"] = sys_src
            self.source_types["system"] = "system"
            self.last_sync["system"] = 0
            logger.info("System source connected")

    def collect_all(self) -> list[CollectedData]:
        """Run a full collection cycle across all sources."""
        results = []
        for name, source in self.sources.items():
            # Track source health before collection
            self.source_healthy[name] = source.connect()
            since = self.last_sync.get(name, 0)
            data = source.collect(since)
            if data.last_sync_time > 0:
                self.last_sync[name] = data.last_sync_time
            results.append(data)

            if data.agents:
                self._persist_agents(name, data.agents)
            self._persist_data(name, data)

        self._build_relationships()
        self._mark_stale_agents()
        self._aggregate_daily_stats()
        self._publish_events(results)

        # 对话日志：从支持 LogAdapter 的来源采集 Turn
        for name, source in self.sources.items():
            if isinstance(source, LogAdapter):
                try:
                    turns = source.parse_turns(self.last_sync.get(name, 0))
                    if turns:
                        self._persist_turns(name, turns)
                except Exception as e:
                    logger.warning(f"Turn parsing failed for '{name}': {e}")

        self._sync_tasks_from_handoffs()

        # 清理过期日志（归档+删除+VACUUM）
        self._archive_and_cleanup()

        return results

    def _publish_events(self, results: list[CollectedData]):
        """Push detailed activity events to the SSE event bus."""
        try:
            import time

            from myagentwatch.event_bus import event_bus

            now = int(time.time() * 1000)
            for data in results:
                # Build message_id → agent mapping for parts
                msg_agent = {}
                for m in data.messages:
                    msg_agent[m.id] = m.agent

                # Message-level events (assistant response / user input)
                for m in data.messages:
                    event_bus.publish("activity", {
                        "id": m.id or f"msg_{now}",
                        "session_id": m.session_id,
                        "agent": m.agent,
                        "event_type": f"message_{m.role}",
                        "severity": "info",
                        "timestamp": m.time_created or now,
                        "model_id": m.model_id,
                        "finish": m.finish,
                        "tokens_input": m.tokens_input,
                        "tokens_output": m.tokens_output,
                        "tokens_reasoning": m.tokens_reasoning,
                        "cache_read": m.cache_read,
                        "cache_write": m.cache_write,
                    })

                # Part-level events with full detail
                for p in data.parts:
                    part_agent = msg_agent.get(p.message_id, "")
                    base = {
                        "id": p.id,
                        "session_id": p.session_id,
                        "timestamp": p.time_created or now,
                        "tokens_input": p.tokens_input,
                        "tokens_output": p.tokens_output,
                        "agent": part_agent,
                    }

                    if p.part_type == "tool" and p.tool_name:
                        sev = "error" if p.tool_status in ("failed", "error") else "info"
                        event_bus.publish("activity", {
                            **base,
                            "event_type": "tool_call",
                            "tool_name": p.tool_name,
                            "tool_status": p.tool_status or "running",
                            "tool_duration_ms": p.tool_duration_ms,
                            "tool_exit_code": p.tool_exit_code,
                            "description": p.tool_description or "",
                            "severity": sev,
                        })

                    elif p.part_type == "thinking" and p.text_content:
                        event_bus.publish("activity", {
                            **base,
                            "event_type": "thinking",
                            "text_snippet": p.text_content[:2000],
                            "text_full": p.text_content,
                            "step_type": p.step_type or "",
                            "severity": "info",
                        })

                    elif p.part_type == "text" and p.text_content:
                        event_bus.publish("activity", {
                            **base,
                            "event_type": "response",
                            "text_snippet": p.text_content[:2000],
                            "text_full": p.text_content,
                            "severity": "info",
                        })

                    elif p.part_type == "step" and p.text_content:
                        event_bus.publish("activity", {
                            **base,
                            "event_type": "thinking",
                            "text_snippet": p.text_content[:2000],
                            "text_full": p.text_content,
                            "step_type": p.step_type or p.step_reason or "",
                            "severity": "info",
                        })
        except Exception:
            pass  # Event bus is optional

    def discover_all_agents(self) -> list[dict]:
        """Discover agents from all sources and persist them."""
        all_agents = []
        for name, source in self.sources.items():
            agents = source.discover_agents()
            all_agents.extend(self._persist_agents(name, agents))
        return all_agents

    def _persist_agents(self, source_name: str, agents) -> list[dict]:
        with database() as conn:
            now = int(time.time() * 1000)
            result = []

            row = conn.execute(
                "SELECT id FROM data_sources WHERE name = ?", (source_name,)
            ).fetchone()
            source_id = (
                row["id"]
                if row
                else self._ensure_source(
                    conn, source_name, self.source_types.get(source_name, "unknown")
                )
            )

            for agent in agents:
                display = agent.display_name or agent.name
                group = agent.group_name or ""

                meta = self.config.get("agent_meta", {}).get(agent.name, {})
                if meta.get("display_name"):
                    display = meta["display_name"]
                if meta.get("group"):
                    group = meta["group"]

                agent_id = f"{source_name}:{agent.name}:{agent.model_id}"
                existing = conn.execute(
                    "SELECT status FROM agents WHERE id = ?", (agent_id,)
                ).fetchone()

                if existing:
                    # Preserve current status; only update metadata/timestamps
                    conn.execute(
                        """UPDATE agents SET display_name=?, group_name=?, agent_type=?,
                           model_id=?, provider_id=?, last_seen_time=?, updated_at=?
                           WHERE id=?""",
                        (display, group, agent.agent_type, agent.model_id,
                         agent.provider_id, agent.last_seen_time, now, agent_id),
                    )
                else:
                    # New agent → idle (yellow, waiting for first heartbeat per user rule 7)
                    conn.execute(
                        """INSERT INTO agents
                           (id, name, display_name, source_id, group_name, agent_type,
                            model_id, provider_id, status, last_seen_time, metadata,
                            created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?, '{}', ?, ?)""",
                        (agent_id, agent.name, display, source_id, group,
                         agent.agent_type, agent.model_id, agent.provider_id,
                         agent.last_seen_time, now, now),
                    )
                result.append(
                    {
                        "id": agent_id,
                        "name": agent.name,
                        "display_name": display,
                        "group": group,
                        "status": existing["status"] if existing else "idle",
                    }
                )

            conn.commit()
            logger.info(f"Persisted {len(result)} agents from {source_name}")
        return result

    def _persist_data(self, source_name: str, data: CollectedData):
        if not data.sessions and not data.messages and not data.parts:
            return

        with database() as conn:
            self._ensure_source(
                conn, source_name, self.source_types.get(source_name, "unknown")
            )

            msg_agent_map = {}
            session_agent_map = {}
            for m in data.messages:
                agent_id = f"{source_name}:{m.agent}:{m.model_id}"
                msg_agent_map[m.id] = agent_id
                if m.session_id not in session_agent_map:
                    session_agent_map[m.session_id] = agent_id

            for s in data.sessions:
                s_agent_id = session_agent_map.get(s.id, "")
                if not s_agent_id:
                    continue
                conn.execute(
                    """INSERT OR REPLACE INTO sessions
                       (id, agent_id, title, slug, directory, status, parent_id,
                        time_created, time_updated)
                       VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
                    (
                        s.id,
                        s_agent_id,
                        s.title,
                        s.slug,
                        s.directory,
                        s.parent_id,
                        s.time_created,
                        s.time_updated,
                    ),
                )

            for m in data.messages:
                agent_id = msg_agent_map.get(
                    m.id, f"{source_name}:{m.agent}:{m.model_id}"
                )
                conn.execute(
                    """INSERT OR IGNORE INTO token_records
                       (session_id, agent_id, message_id, part_id, model_id, provider_id,
                        tokens_input, tokens_output, tokens_reasoning, cache_read, cache_write,
                        cost, timestamp)
                       VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        m.session_id,
                        agent_id,
                        m.id,
                        m.model_id,
                        m.provider_id,
                        m.tokens_input,
                        m.tokens_output,
                        m.tokens_reasoning,
                        m.cache_read,
                        m.cache_write,
                        m.cost,
                        m.time_created,
                    ),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO activity_log
                       (session_id, agent_id, event_type, data, severity, timestamp)
                       VALUES (?, ?, ?, ?, 'info', ?)""",
                    (
                        m.session_id,
                        agent_id,
                        f"message_{m.role}",
                        f'{{"finish":"{m.finish}"}}',
                        m.time_created,
                    ),
                )

            for p in data.parts:
                p_agent_id = msg_agent_map.get(p.message_id, "")
                if p.part_type == "tool" and p.tool_name:
                    conn.execute(
                        """INSERT OR IGNORE INTO tool_calls
                           (session_id, agent_id, message_id, part_id, tool_name,
                            call_id, status, description, exit_code, duration_ms,
                            error_output, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            p.session_id,
                            p_agent_id,
                            p.message_id,
                            p.id,
                            p.tool_name,
                            p.call_id,
                            p.tool_status,
                            p.tool_description,
                            p.tool_exit_code,
                            p.tool_duration_ms,
                            "",
                            p.time_created,
                        ),
                    )
                conn.execute(
                    """INSERT OR IGNORE INTO activity_log
                       (session_id, agent_id, event_type, data, severity, timestamp)
                       VALUES (?, ?, ?, ?, 'info', ?)""",
                    (
                        p.session_id,
                        p_agent_id,
                        f"part_{p.part_type}",
                        f'{{"type":"{p.part_type}"}}',
                        p.time_created,
                    ),
                )

            conn.commit()

    def _ensure_source(self, conn, name: str, source_type: str = "opencode_db") -> int:
        now = int(time.time() * 1000)
        conn.execute(
            "INSERT OR IGNORE INTO data_sources (name, source_type, db_path, enabled, created_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (name, source_type, "", now),
        )
        row = conn.execute(
            "SELECT id FROM data_sources WHERE name = ?", (name,)
        ).fetchone()
        conn.commit()
        return row["id"]

    def get_health(self) -> list[dict]:
        results = []
        for _name, source in self.sources.items():
            results.append(source.health_check())
        return results

    def get_active_agent_count(self) -> int:
        with database() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM agents WHERE status = 'active'"
            ).fetchone()
            return row["cnt"] if row else 0

    def _agent_needs_model(self, row) -> bool:
        """Return True if this agent type requires a model to function."""
        agent_type = (row["agent_type"] or "").lower() if row else ""
        no_model_types = {"system", "log_file", "cli", ""}
        return agent_type not in no_model_types

    def _process_role_keys(self, row, source_row) -> set[str]:
        """Possible process roles for an agent.

        Process reports come from myagentwatch-cli and use simple roles such as
        "claude-code" or "codex". Agent rows can use source names, source
        types, or agent types, so normalize all likely keys.
        """
        keys = set()
        if source_row:
            keys.add(source_row["name"] or "")
            keys.add(source_row["source_type"] or "")
        keys.add(row["agent_type"] or "")
        keys.add(row["group_name"] or "")
        normalized = set()
        for key in keys:
            value = (key or "").strip().lower().replace("_", "-").replace(" ", "-")
            if value:
                normalized.add(value)
        return normalized

    def _mark_stale_agents(self):
        """State machine (5 states):
        🟢 active  = recent heartbeat/activity + no errors + model OK
        🔵 working = agent explicitly reports "working" status via heartbeat
        🟡 idle    = new agent waiting first heartbeat / stale activity / uncertain
        🔴 error   = model missing for agents that need one / recent errors
        🟠 blocked = persistent errors beyond 2x timeout (needs intervention)
        🟣 offline = source gone / never started / timeout / updating
        Only fully removed agents (not in any source) disappear from display.
        """
        timeout_sec = self.config.get("heartbeat_timeout", 300)
        timeout_ms = timeout_sec * 1000
        offline_timeout_ms = timeout_ms * 2
        now = int(time.time() * 1000)
        cutoff = now - timeout_ms
        offline_cutoff = now - offline_timeout_ms

        with database() as conn:
            # Primary liveness: explicit heartbeats
            latest_heartbeats = {}
            for r in conn.execute(
                "SELECT id, last_heartbeat_at FROM agents WHERE last_heartbeat_at > 0"
            ):
                latest_heartbeats[r["id"]] = r["last_heartbeat_at"]

            # Fallback: activity_log for agents without heartbeat support
            latest_activity = {}
            for r in conn.execute(
                "SELECT agent_id, MAX(timestamp) as last_ts FROM activity_log GROUP BY agent_id"
            ):
                latest_activity[r["agent_id"]] = r["last_ts"]

            # Latest error per agent
            latest_errors = {}
            for r in conn.execute(
                "SELECT agent_id, MAX(timestamp) as last_err FROM activity_log "
                "WHERE severity IN ('error','critical') GROUP BY agent_id"
            ):
                latest_errors[r["agent_id"]] = r["last_err"]

            # Process-level liveness from myagentwatch-cli daemon.
            # A recent process means the Agent runtime exists, but is not
            # necessarily doing work, so it should fall back to idle/waiting
            # rather than active/online.
            latest_process_roles = {}
            try:
                for r in conn.execute(
                    "SELECT detected_role, MAX(timestamp) as last_ts "
                    "FROM agent_processes "
                    "WHERE detected_role IS NOT NULL AND detected_role != '' "
                    "GROUP BY detected_role"
                ):
                    role = (r["detected_role"] or "").strip().lower().replace("_", "-")
                    if role:
                        latest_process_roles[role] = r["last_ts"]
            except Exception:
                latest_process_roles = {}

            rows = conn.execute(
                "SELECT id, name, source_id, group_name, model_id, agent_type, "
                "last_seen_time, last_heartbeat_at, created_at, status FROM agents "
                "WHERE status != 'removed'"
            ).fetchall()

            for row in rows:
                hb = latest_heartbeats.get(row["id"], 0)
                # Use the most recent of: heartbeat, activity_log, or source discovery
                seen = row["last_seen_time"] or 0
                actual_last = max(hb, latest_activity.get(row["id"], 0), seen)
                if actual_last == 0:
                    actual_last = seen
                last_err = latest_errors.get(row["id"], 0)
                created = row["created_at"] or 0
                needs_model = self._agent_needs_model(row)
                prev_status = row["status"]
                new_status = None
                reason = ""

                # ── 1. Source-level checks ──
                source_gone = False
                source_row = None
                if row["source_id"]:
                    src = conn.execute(
                        "SELECT name, source_type, enabled FROM data_sources WHERE id = ?",
                        (row["source_id"],),
                    ).fetchone()
                    if src:
                        source_row = src
                        if not src["enabled"]:
                            source_gone = True
                            reason = "source_disabled"
                        elif src["name"] not in self.source_healthy:
                            source_gone = True
                            reason = "source_removed"
                        elif not self.source_healthy[src["name"]]:
                            source_gone = True
                            reason = "source_disconnected"
                    else:
                        source_gone = True
                        reason = "source_removed"

                process_last = 0
                for role in self._process_role_keys(row, source_row):
                    process_last = max(process_last, latest_process_roles.get(role, 0) or 0)
                has_recent_process = process_last > 0 and process_last >= cutoff

                has_recent = actual_last > 0 and actual_last >= cutoff
                has_recent_err = last_err > 0 and last_err >= cutoff
                was_working = prev_status == "working"
                persistent_error = prev_status == "error" and actual_last < offline_cutoff and actual_last > 0
                is_stale = actual_last > 0 and actual_last < cutoff
                is_deep_stale = actual_last > 0 and actual_last < offline_cutoff
                never_active = actual_last == 0
                is_new = never_active and created > cutoff

                if source_gone:
                    if has_recent_process and reason == "source_disconnected":
                        new_status = "idle"
                        reason = "process_detected_source_disconnected"
                    else:
                        new_status = "offline"
                elif has_recent:
                    if hb > 0 and hb >= cutoff and prev_status in ("working", "blocked", "idle"):
                        new_status = prev_status
                        reason = f"reported_{prev_status}"
                    elif has_recent_err:
                        new_status = "error"
                        reason = "runtime_error"
                    elif needs_model and not row["model_id"]:
                        new_status = "error"
                        reason = "model_missing"
                    elif prev_status == "working":
                        # Agent was working, still has recent heartbeat — stay working
                        new_status = "working"
                    else:
                        new_status = "active"
                elif is_stale:
                    if persistent_error:
                        new_status = "blocked"
                        reason = "persistent_error"
                    elif needs_model and not row["model_id"]:
                        new_status = "error"
                        reason = "model_missing"
                    elif is_deep_stale:
                        # If the freshest signal is also deeply stale, the agent
                        # is not waiting; it is not currently running.
                        if has_recent_process:
                            new_status = "idle"
                            reason = "process_detected_waiting"
                        else:
                            new_status = "offline"
                            reason = "heartbeat_lost" if hb > 0 and actual_last == hb else "activity_lost"
                    else:
                        new_status = "idle"
                elif never_active:
                    if has_recent_process:
                        new_status = "idle"
                        reason = "process_detected_waiting"
                    elif is_new:
                        new_status = "idle"
                        reason = "awaiting_first_heartbeat"
                    else:
                        if needs_model and not row["model_id"]:
                            new_status = "error"
                            reason = "model_missing"
                        else:
                            new_status = "offline"
                            reason = "never_started"

                # Apply status change
                if new_status and new_status != prev_status:
                    conn.execute(
                        "UPDATE agents SET status = ?, status_since = ?, "
                        "metadata = json_set(COALESCE(metadata, '{}'), '$.status_reason', ?) "
                        "WHERE id = ?",
                        (new_status, now, reason, row["id"]),
                    )
                    logger.info(
                        f"Agent '{row['name']}': {prev_status} → {new_status} "
                        f"(reason={reason}, heartbeat={hb}, last_activity={actual_last}, cutoff={cutoff})"
                    )

            conn.commit()

    def _build_relationships(self):
        """Build agent_relationships from session parent→child links."""
        with database() as conn:
            now = int(time.time() * 1000)

            try:
                # Parent→child from session tree
                rows = conn.execute(
                    "SELECT DISTINCT s1.agent_id as source_id, s2.agent_id as target_id "
                    "FROM sessions s1 "
                    "JOIN sessions s2 ON s2.parent_id = s1.id "
                    "WHERE s1.agent_id != '' AND s2.agent_id != '' "
                    "  AND s1.agent_id != s2.agent_id"
                ).fetchall()

                for row in rows:
                    conn.execute(
                        """INSERT OR REPLACE INTO agent_relationships
                           (source_agent_id, target_agent_id, relation_type, call_count, last_seen)
                           VALUES (?, ?, 'parent_child',
                           COALESCE((SELECT call_count + 1 FROM agent_relationships
                                     WHERE source_agent_id = ? AND target_agent_id = ?
                                     AND relation_type = 'parent_child'), 1),
                           ?)""",
                        (
                            row["source_id"],
                            row["target_id"],
                            row["source_id"],
                            row["target_id"],
                            now,
                        ),
                    )

                conn.commit()
            except Exception as e:
                logger.error(f"Error building relationships: {e}")

    def _existing_natural_keys(self, conn, keys: list[str]) -> set[str]:
        """批量检查已存在的 natural_key，用于去重。"""
        if not keys:
            return set()
        placeholders = ",".join(["?"] * len(keys))
        rows = conn.execute(
            f"SELECT natural_key FROM conversation_turns WHERE natural_key IN ({placeholders})",
            keys,
        ).fetchall()
        return {r["natural_key"] for r in rows}

    def _persist_turns(self, source_name: str, turns):
        """批量持久化 Turn 及其 ContentBlock。

        使用 executemany 批量写入，避免逐条 INSERT 导致的 IO 风暴。
        natural_key UNIQUE + 内存去重保证不重复。
        """
        if not turns:
            return

        with database() as conn:
            # 去重：查询已存在的 natural_key
            natural_keys = [t.natural_key for t in turns]
            existing = self._existing_natural_keys(conn, natural_keys)
            new_turns = [t for t in turns if t.natural_key not in existing]
            if not new_turns:
                return

            now = int(time.time() * 1000)

            # 1. 先批量插入 conversation_turns (handoff_id 暂为 NULL)
            turn_rows = []
            for t in new_turns:
                turn_rows.append((
                    t.natural_key, t.agent_id, t.session_id, t.trace_id,
                    t.seq, t.phase, t.role, None, t.source_type,
                    t.severity, t.token_count, t.duration_ms,
                    t.time_start, t.time_end or t.time_start,
                ))

            conn.executemany(
                """INSERT OR IGNORE INTO conversation_turns
                   (natural_key, agent_id, session_id, trace_id,
                    seq, phase, role, handoff_id, source_type,
                    severity, token_count, duration_ms,
                    time_start, time_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                turn_rows,
            )

            # 2. 查询 turn IDs
            turn_id_map: dict[str, int] = {}
            for t in new_turns:
                row = conn.execute(
                    "SELECT id FROM conversation_turns WHERE natural_key = ?",
                    (t.natural_key,),
                ).fetchone()
                if row:
                    turn_id_map[t.natural_key] = row["id"]

            # 3. 批量插入 agent_handoffs，收集 handoff_id 回写
            handoff_rows = []
            handoff_to_turn_natural: list[tuple] = []  # (natural_key, handoff params)
            for t in new_turns:
                if not t.handoff:
                    continue
                handoff_rows.append((
                    t.session_id, t.trace_id, t.handoff.from_agent_id,
                    t.handoff.to_agent_id, turn_id_map.get(t.natural_key),
                    t.handoff.to_session_id, t.handoff.prompt, t.handoff.result,
                    t.handoff.subagent_type, t.handoff.status,
                    t.time_start, t.time_end or t.time_start,
                ))
                handoff_to_turn_natural.append(t.natural_key)

            if handoff_rows:
                cursor = conn.executemany(
                    """INSERT INTO agent_handoffs
                       (session_id, trace_id, from_agent_id, to_agent_id,
                        from_turn_id, to_session_id, prompt_text, result_text,
                        subagent_type, status, time_start, time_end)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    handoff_rows,
                )
                # 回写 handoff_id 到 conversation_turns
                last_id = cursor.lastrowid
                for i, natural_key in enumerate(handoff_to_turn_natural):
                    handoff_db_id = last_id + i
                    conn.execute(
                        "UPDATE conversation_turns SET handoff_id = ? WHERE natural_key = ?",
                        (handoff_db_id, natural_key),
                    )

            # 4. 批量插入 turn_content
            content_rows = []
            for t in new_turns:
                db_turn_id = turn_id_map.get(t.natural_key)
                if not db_turn_id:
                    continue
                for block in t.blocks:
                    content_rows.append((
                        db_turn_id, block.block_type, block.content,
                        block.tool_name, block.tool_call_id,
                        block.mime_type, block.char_count,
                    ))

            if content_rows:
                conn.executemany(
                    """INSERT OR IGNORE INTO turn_content
                       (turn_id, block_type, content, tool_name,
                        tool_call_id, mime_type, char_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    content_rows,
                )

            # 5. 更新采集进度（只写一次，取最大 seq）
            if new_turns:
                max_seq = max(t.seq for t in new_turns)
                conn.execute(
                    """INSERT OR REPLACE INTO collector_progress
                       (source_name, file_path, byte_offset, last_turn_seq, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (source_name, source_name, 0, max_seq, now),
                )

            conn.commit()
            logger.info(
                f"Persisted {len(new_turns)} turns ({len(content_rows)} content blocks, "
                f"{len(handoff_rows)} handoffs) from {source_name}"
            )

    def _sync_tasks_from_handoffs(self):
        """Create task records from Agent handoffs and auto-track status."""
        try:
            with database() as conn:
                from myagentwatch.tasks import auto_track_tasks, create_tasks_from_handoffs

                created = create_tasks_from_handoffs(conn)
                changed = auto_track_tasks(
                    conn,
                    heartbeat_timeout_sec=self.config.get("heartbeat_timeout", 300),
                )
                conn.commit()
            if created:
                logger.info(f"Created {created} tasks from agent handoffs")
            if changed:
                logger.info(f"Auto-tracked {len(changed)} task status changes")
        except Exception as e:
            logger.warning(f"Task sync from handoffs failed: {e}")

    _last_aggregate_date = ""

    def _aggregate_daily_stats(self):
        """Roll up token_records → daily_stats. Only runs once per day."""
        import time as _time
        today = _time.strftime("%Y-%m-%d")
        if today == self.__class__._last_aggregate_date:
            return
        self.__class__._last_aggregate_date = today
        with database() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO daily_stats "
                "(agent_id, date, tokens_input, tokens_output, tokens_reasoning, "
                "cache_read, cache_write, total_cost, message_count, "
                "tool_call_count, success_count, error_count) "
                "SELECT agent_id, date(timestamp / 1000, 'unixepoch'), "
                "COALESCE(SUM(tokens_input), 0), "
                "COALESCE(SUM(tokens_output), 0), "
                "COALESCE(SUM(tokens_reasoning), 0), "
                "COALESCE(SUM(cache_read), 0), "
                "COALESCE(SUM(cache_write), 0), "
                "COALESCE(SUM(cost), 0), "
                "COUNT(DISTINCT message_id), "
                "0, 0, 0 "
                "FROM token_records "
                "WHERE date(timestamp / 1000, 'unixepoch') = ? "
                "GROUP BY agent_id",
                (today,),
            )
            # Backfill tool counts for today
            conn.execute(
                "UPDATE daily_stats SET "
                "tool_call_count = (SELECT COUNT(*) FROM tool_calls "
                "WHERE tool_calls.agent_id = daily_stats.agent_id "
                "AND date(tool_calls.timestamp / 1000, 'unixepoch') = ?), "
                "success_count = (SELECT COUNT(*) FROM tool_calls "
                "WHERE tool_calls.agent_id = daily_stats.agent_id "
                "AND status = 'success' "
                "AND date(tool_calls.timestamp / 1000, 'unixepoch') = ?), "
                "error_count = (SELECT COUNT(*) FROM tool_calls "
                "WHERE tool_calls.agent_id = daily_stats.agent_id "
                "AND status IN ('error', 'failed') "
                "AND date(tool_calls.timestamp / 1000, 'unixepoch') = ?) "
                "WHERE date = ?",
                (today, today, today, today),
            )
            conn.commit()

    def _archive_and_cleanup(self):
        """归档+清理策略：
        - log_archive_days (默认 7): 超过此天数的 turn 导出为 gzip JSON，从主表删除
        - log_retention_days (默认 365): 超过此天数的数据彻底删除
        - 归档后 VACUUM 回收磁盘空间
        """
        archive_days = self.config.get("log_archive_days", 7)
        retention_days = self.config.get("log_retention_days", 365)
        now = int(time.time() * 1000)

        # 需要清理和归档的数据量很大时跳过，只在空闲时做
        should_vacuum = False

        with database() as conn:
            # ── 1. 归档：archived_days 之外的数据导出为 gzip ──
            if archive_days > 0:
                archive_cutoff = now - archive_days * 86400 * 1000
                archive_turns = conn.execute(
                    "SELECT id, natural_key, agent_id, session_id, trace_id, "
                    "seq, phase, role, source_type, severity, token_count, "
                    "duration_ms, time_start, time_end "
                    "FROM conversation_turns WHERE time_start < ?",
                    (archive_cutoff,),
                ).fetchall()

                if archive_turns:
                    self._export_turns_to_archive(conn, archive_turns, archive_days)
                    should_vacuum = True

            # ── 2. 彻底删除：超过 retention_days 的数据 ──
            if retention_days > 0:
                purge_cutoff = now - retention_days * 86400 * 1000
                old_ids = [
                    r["id"] for r in conn.execute(
                        "SELECT id FROM conversation_turns WHERE time_start < ?",
                        (purge_cutoff,),
                    ).fetchall()
                ]

                if old_ids:
                    for batch_start in range(0, len(old_ids), 500):
                        batch = old_ids[batch_start:batch_start + 500]
                        ph = ",".join(["?"] * len(batch))
                        conn.execute(f"DELETE FROM turn_content WHERE turn_id IN ({ph})", batch)
                        conn.execute(f"DELETE FROM conversation_turns WHERE id IN ({ph})", batch)

                    conn.execute(
                        "DELETE FROM agent_handoffs WHERE time_start < ?",
                        (purge_cutoff,),
                    )
                    logger.info(f"Purged {len(old_ids)} turns (retention={retention_days}d)")
                    should_vacuum = True

            conn.commit()

            # ── 3. VACUUM 回收空间 ──
            if should_vacuum:
                conn.execute("VACUUM")
                logger.info("VACUUM complete — disk space reclaimed")

    def _export_turns_to_archive(self, conn, turns, archive_days: int):
        """将旧 turn 数据导出为 gzip JSON 归档，然后从主表删除。"""
        import gzip
        import json
        import os

        archive_dir = os.path.join(os.path.dirname(__file__), "..", "data", "archive")
        os.makedirs(archive_dir, exist_ok=True)

        # 按年月分文件
        month_key = time.strftime("%Y-%m", time.gmtime(time.time() - archive_days * 86400))
        archive_path = os.path.join(archive_dir, f"turns-{month_key}.jsonl.gz")

        turn_ids = [r["id"] for r in turns]
        written = 0

        with gzip.open(archive_path, "at", encoding="utf-8") as f:
            for turn in turns:
                # 联表查 content blocks
                blocks = conn.execute(
                    "SELECT block_type, content, tool_name, tool_call_id, mime_type "
                    "FROM turn_content WHERE turn_id = ? ORDER BY id",
                    (turn["id"],),
                ).fetchall()

                entry = {
                    "natural_key": turn["natural_key"],
                    "agent_id": turn["agent_id"],
                    "session_id": turn["session_id"],
                    "trace_id": turn["trace_id"],
                    "seq": turn["seq"],
                    "phase": turn["phase"],
                    "role": turn["role"],
                    "source_type": turn["source_type"],
                    "severity": turn["severity"],
                    "token_count": turn["token_count"],
                    "duration_ms": turn["duration_ms"],
                    "time_start": turn["time_start"],
                    "time_end": turn["time_end"],
                    "blocks": [dict(b) for b in blocks],
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                written += 1

        # 删除已归档的 content 和 turns
        for batch_start in range(0, len(turn_ids), 500):
            batch = turn_ids[batch_start:batch_start + 500]
            ph = ",".join(["?"] * len(batch))
            conn.execute(f"DELETE FROM turn_content WHERE turn_id IN ({ph})", batch)
            conn.execute(f"DELETE FROM conversation_turns WHERE id IN ({ph})", batch)

        logger.info(
            f"Archived {written} turns to {archive_path} "
            f"(archive_days={archive_days})"
        )
