"""Tests for query helpers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_database_initialization():
    """Test that init_db creates tables successfully."""
    from myagentwatch.db import get_connection, init_db
    init_db()
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t[0] for t in tables]
    expected = [
        "activity_log",
        "agent_relationships",
        "agents",
        "alerts",
        "data_sources",
        "daily_stats",
        "health_checks",
        "sessions",
        "template_config",
        "token_records",
        "tool_calls",
    ]
    for name in expected:
        assert name in table_names, f"Missing table: {name}"


def test_queries_import():
    """Test that all query functions are importable."""
    from myagentwatch.queries import (
        query_overview_cards,
        query_topology,
    )

    assert callable(query_overview_cards)
    assert callable(query_topology)
