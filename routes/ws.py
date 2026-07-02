"""MyAgentWatch WebSocket Push — snapshot broadcast logic."""

import logging
import time

from myagentwatch.db import database
from myagentwatch.queries import (
    query_agents_active,
    query_chart_data,
    query_overview_cards,
    query_topology,
    query_tree,
)

logger = logging.getLogger("myagentwatch.ws_push")


def build_snapshot() -> dict:
    """Build the full stat_snapshot payload."""
    try:
        with database() as conn:
            cards = query_overview_cards(conn)
            agents = query_agents_active(conn)
            charts = query_chart_data(conn)
            topology = query_topology(conn)
            tree = query_tree(conn)

            log_entries = conn.execute(
                "SELECT id, session_id, agent_id, event_type, severity, timestamp "
                "FROM activity_log ORDER BY timestamp DESC LIMIT 50"
            ).fetchall()

        return {
            **cards,
            "agents": agents,
            "tokens_by_agent": charts["tokens_by_agent"],
            "latency": charts["latency"],
            "hourly_tokens": charts.get("hourly_tokens", []),
            "topology": topology,
            "tree": tree,
            "activity_log": [dict(e) for e in log_entries],
            "timestamp": int(time.time() * 1000),
        }
    except Exception as e:
        logger.error(f"Snapshot build error: {e}")
        return {}


def build_agent_delta(agent_id: str) -> dict:
    """Build an incremental delta for a single agent."""
    try:
        with database() as conn:
            agent = conn.execute(
                "SELECT id, name, display_name, group_name, agent_type, "
                "model_id, provider_id, status, last_heartbeat_at, "
                "last_seen_time, metadata, updated_at "
                "FROM agents WHERE id = ?",
                (agent_id,),
            ).fetchone()
            if not agent:
                return {}

            tokens = conn.execute(
                "SELECT COALESCE(SUM(tokens_input), 0) as inp, "
                "COALESCE(SUM(tokens_output), 0) as outp, "
                "COALESCE(SUM(cost), 0) as cost "
                "FROM token_records WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()

        return {
            "agent_id": agent_id,
            "status": agent["status"],
            "last_heartbeat_at": agent["last_heartbeat_at"],
            "tokens_input": tokens["inp"],
            "tokens_output": tokens["outp"],
            "cost": round(tokens["cost"], 6),
            "timestamp": int(time.time() * 1000),
        }
    except Exception as e:
        logger.error(f"Agent delta build error ({agent_id}): {e}")
        return {}
