"""Test query_topology doesn't throw SQL syntax errors (B2 regression)."""

import time

from myagentwatch.db import SCHEMA


def test_query_topology_no_syntax_error(mem_db):
    """query_topology() should not raise sqlite3.OperationalError."""
    mem_db.executescript(SCHEMA)

    now = int(time.time() * 1000)

    # Seed minimal data: two agents with sessions
    mem_db.execute(
        "INSERT INTO agents (id, name, status, last_seen_time) VALUES (?, ?, 'active', ?)",
        ("test:plan:gpt4", "plan", now),
    )
    mem_db.execute(
        "INSERT INTO agents (id, name, status, last_seen_time) VALUES (?, ?, 'active', ?)",
        ("test:build:gpt4", "build", now),
    )

    # Parent session
    mem_db.execute(
        "INSERT INTO sessions (id, agent_id, status, time_created, time_updated) "
        "VALUES ('s1', 'test:plan:gpt4', 'active', ?, ?)",
        (now, now),
    )
    # Child session
    mem_db.execute(
        "INSERT INTO sessions (id, agent_id, status, parent_id, time_created, time_updated) "
        "VALUES ('s2', 'test:build:gpt4', 'active', 's1', ?, ?)",
        (now, now),
    )
    mem_db.commit()

    from myagentwatch.queries import query_topology
    result = query_topology(mem_db)

    assert "nodes" in result
    assert "edges" in result
    assert len(result["nodes"]) >= 2
    assert len(result["edges"]) >= 1
