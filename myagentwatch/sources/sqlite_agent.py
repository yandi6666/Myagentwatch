"""Generic SQLite Agent data source adapter.

For any tool that stores agent activity in a SQLite database.
Configure via config.yaml — zero code for most common tools.

Supports: n8n, OpenCode, any custom SQLite-based agent tool.
"""

import json
import logging
import os
import re
import sqlite3
import time
from typing import Any

from . import register_source
from .base import (
    AgentInfo,
    CollectedData,
    MessageInfo,
    PartInfo,
    SessionInfo,
    SourceInterface,
)

logger = logging.getLogger("myagentwatch.source.sqlite_agent")

_IDENT_RE = re.compile(r"^[a-zA-Z_]\w*$")


def _safe_ident(name: str) -> str:
    """Validate a SQL identifier, raise ValueError if invalid."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


@register_source("sqlite_agent")
class SQLiteAgentSource(SourceInterface):
    """Generic adapter for any SQLite-backed agent tool.

    Config YAML keys (all optional except db_path):
        db_path:         path to SQLite database
        agent_table:     table with agent activity rows (default: uses agent_query)
        agent_query:     SQL to discover agents; returns columns (name, model_id, provider_id, agent_type)
        session_table:   table name for sessions (default: "session")
        message_table:   table name for messages (default: "message")
        part_table:      table name for parts/tool_calls (default: "part")
        time_column:     timestamp col for incremental sync (default: "time_updated")
        json_column:     column name containing JSON data (default: "data")
        incremental:     whether to use incremental sync (default: true)
    """

    def __init__(self, name: str, db_path: str, **kwargs):
        self.name = name
        self.db_path = os.path.expanduser(db_path)
        self._exists = os.path.exists(self.db_path)

        self.agent_query = kwargs.get("agent_query", "")
        self.session_table = kwargs.get("session_table", "session")
        self.message_table = kwargs.get("message_table", "message")
        self.part_table = kwargs.get("part_table", "part")
        self.time_column = kwargs.get("time_column", "time_updated")
        self.json_column = kwargs.get("json_column", "data")
        self.incremental = kwargs.get("incremental", True)
        self._columns_checked = False
        self._table_time_cols = {}

    def _check_columns(self):
        if self._columns_checked or not self._exists:
            return
        try:
            conn = self._open_readonly()
            for table in (self.session_table, self.message_table, self.part_table):
                try:
                    cols = conn.execute(f"PRAGMA table_info({_safe_ident(table)})").fetchall()
                    col_names = {c["name"] for c in cols}
                    self._table_time_cols[table] = (
                        self.time_column
                        if self.time_column in col_names
                        else "time_created"
                    )
                except Exception:
                    self._table_time_cols[table] = "time_created"
            conn.close()
            self._columns_checked = True
        except Exception:
            for table in (self.session_table, self.message_table, self.part_table):
                self._table_time_cols[table] = "time_created"
            self._columns_checked = True

    def connect(self) -> bool:
        self._exists = os.path.exists(self.db_path)
        if not self._exists:
            logger.warning(f"Database not found: {self.db_path}")
        return self._exists

    def _open_readonly(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def discover_agents(self) -> list[AgentInfo]:
        if not self._exists:
            return []

        agents = []
        try:
            conn = self._open_readonly()

            if self.agent_query:
                rows = conn.execute(self.agent_query).fetchall()
                seen = set()
                for row in rows:
                    d = dict(row)
                    name = d.get("name", d.get("agent_name", ""))
                    if not name:
                        continue
                    key = f"{name}:{d.get('model_id', '')}:{d.get('provider_id', '')}"
                    if key in seen:
                        continue
                    seen.add(key)
                    agents.append(
                        AgentInfo(
                            name=name,
                            agent_type=d.get("agent_type", name),
                            model_id=d.get("model_id", ""),
                            provider_id=d.get("provider_id", ""),
                            last_seen_time=int(time.time() * 1000),
                        )
                    )
            else:
                jc = _safe_ident(self.json_column)
                rows = conn.execute(
                    f"SELECT DISTINCT json_extract({jc}, '$.agent') as agent_name, "
                    f"json_extract({jc}, '$.modelID') as model_id, "
                    f"json_extract({jc}, '$.providerID') as provider_id "
                    f"FROM {_safe_ident(self.message_table)} "
                    f"WHERE json_extract({jc}, '$.agent') IS NOT NULL"
                ).fetchall()
                seen = set()
                for row in rows:
                    name = row["agent_name"]
                    if not name:
                        continue
                    model = row["model_id"] or ""
                    provider = row["provider_id"] or ""
                    key = f"{name}:{model}:{provider}"
                    if key in seen:
                        continue
                    seen.add(key)
                    agents.append(
                        AgentInfo(
                            name=name,
                            agent_type=name,
                            model_id=model,
                            provider_id=provider,
                            last_seen_time=int(time.time() * 1000),
                        )
                    )

            conn.close()
            logger.info(f"Discovered {len(agents)} agents from {self.name}")
        except Exception as e:
            logger.error(f"Error discovering agents from {self.name}: {e}")

        return agents

    def collect(self, since_timestamp: int) -> CollectedData:
        data = CollectedData(last_sync_time=since_timestamp)

        if not self._exists:
            return data

        self._check_columns()
        sess_time_col = self._table_time_cols.get(self.session_table, "time_created")
        msg_time_col = self._table_time_cols.get(self.message_table, "time_created")
        part_time_col = self._table_time_cols.get(self.part_table, "time_created")

        try:
            conn = self._open_readonly()

            # --- sessions ---
            rows = conn.execute(
                f"SELECT id, parent_id, title, slug, directory, time_created, "
                f"{_safe_ident(sess_time_col)} as time_updated, summary_additions, summary_deletions "
                f"FROM {_safe_ident(self.session_table)} WHERE {_safe_ident(sess_time_col)} > ?",
                (since_timestamp,),
            ).fetchall()
            for r in rows:
                data.sessions.append(
                    SessionInfo(
                        id=r["id"],
                        parent_id=r["parent_id"],
                        title=r["title"] or "",
                        slug=r["slug"] or "",
                        directory=r["directory"] or "",
                        time_created=r["time_created"],
                        time_updated=r["time_updated"],
                        summary_additions=r["summary_additions"] or 0,
                        summary_deletions=r["summary_deletions"] or 0,
                    )
                )

            # --- messages ---
            rows = conn.execute(
                f"SELECT id, session_id, time_created, {_safe_ident(msg_time_col)} as time_updated, "
                f"{_safe_ident(self.json_column)} "
                f"FROM {_safe_ident(self.message_table)} WHERE {_safe_ident(msg_time_col)} > ?",
                (since_timestamp,),
            ).fetchall()
            for r in rows:
                d = json.loads(r[self.json_column]) if r[self.json_column] else {}
                tokens = d.get("tokens", {})
                cache = tokens.get("cache", {})
                t = d.get("time", {})

                data.messages.append(
                    MessageInfo(
                        id=r["id"],
                        session_id=r["session_id"],
                        role=d.get("role", ""),
                        agent=d.get("agent", ""),
                        mode=d.get("mode", ""),
                        model_id=d.get("modelID", ""),
                        provider_id=d.get("providerID", ""),
                        finish=d.get("finish"),
                        cost=d.get("cost", 0) or 0,
                        tokens_input=tokens.get("input", 0) or 0,
                        tokens_output=tokens.get("output", 0) or 0,
                        tokens_reasoning=tokens.get("reasoning", 0) or 0,
                        cache_read=cache.get("read", 0) or 0,
                        cache_write=cache.get("write", 0) or 0,
                        time_created=r["time_created"],
                        time_completed=t.get("completed"),
                        parent_id=d.get("parentID"),
                    )
                )

            # --- parts ---
            rows = conn.execute(
                f"SELECT id, message_id, session_id, time_created, {_safe_ident(self.json_column)} "
                f"FROM {_safe_ident(self.part_table)} WHERE {_safe_ident(part_time_col)} > ? ORDER BY time_created",
                (since_timestamp,),
            ).fetchall()
            for r in rows:
                d = json.loads(r[self.json_column]) if r[self.json_column] else {}
                pt = d.get("type", "")
                state = d.get("state", {}) or {}
                tokens = d.get("tokens", {}) or {}
                cache = tokens.get("cache", {}) or {}
                tool_time = state.get("time", {}) or {}
                step_tokens = tokens

                duration = 0
                if tool_time.get("start") and tool_time.get("end"):
                    duration = tool_time["end"] - tool_time["start"]

                data.parts.append(
                    PartInfo(
                        id=r["id"],
                        message_id=r["message_id"],
                        session_id=r["session_id"],
                        part_type=pt,
                        tool_name=d.get("tool"),
                        call_id=d.get("callID"),
                        tool_status=state.get("status"),
                        tool_description=state.get("input", {}).get("description")
                        if isinstance(state.get("input"), dict)
                        else None,
                        tool_exit_code=state.get("input", {}).get("exit")
                        if isinstance(state.get("input"), dict)
                        else None,
                        tool_duration_ms=duration,
                        text_content=d.get("text"),
                        step_type="start"
                        if pt == "step-start"
                        else "finish"
                        if pt == "step-finish"
                        else None,
                        step_reason=d.get("reason"),
                        tokens_input=step_tokens.get("input", 0) or 0,
                        tokens_output=step_tokens.get("output", 0) or 0,
                        tokens_reasoning=step_tokens.get("reasoning", 0) or 0,
                        cache_read=cache.get("read", 0) or 0,
                        cache_write=cache.get("write", 0) or 0,
                        cost=d.get("cost", 0) or 0,
                        time_created=r["time_created"],
                    )
                )

            conn.close()
            data.last_sync_time = int(time.time() * 1000)
            logger.info(
                f"Collected from {self.name}: "
                f"{len(data.sessions)} sessions, {len(data.messages)} msgs, "
                f"{len(data.parts)} parts"
            )
        except Exception as e:
            logger.error(f"Error collecting from {self.name}: {e}")

        return data

    def health_check(self) -> dict[str, Any]:
        ok = self._exists and os.access(self.db_path, os.R_OK)
        info = {"name": self.name, "type": "sqlite_agent", "accessible": ok}
        if ok:
            try:
                size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
                info["size_mb"] = round(size_mb, 2)
            except Exception:
                pass
        return info
