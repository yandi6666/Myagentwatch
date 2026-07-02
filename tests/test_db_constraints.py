"""Test foreign key enforcement (B5 regression)."""

import sqlite3

from myagentwatch.db import SCHEMA


def test_foreign_key_rejects_orphan():
    """Inserting a child row without parent must fail with FK ON."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)

    # Try to insert a session referencing a nonexistent agent
    try:
        conn.execute(
            "INSERT INTO sessions (id, agent_id, status, time_created, time_updated) "
            "VALUES ('s_orphan', 'nonexistent', 'active', 0, 0)"
        )
        conn.commit()
        # If we get here, the FK constraint failed to reject
        row = conn.execute(
            "SELECT id FROM sessions WHERE id = 's_orphan'"
        ).fetchone()
        conn.close()
        assert row is None, "FK constraint should have rejected orphan row"
    except sqlite3.IntegrityError:
        # Expected — FK constraint enforced
        conn.close()


def test_foreign_key_cascade_parent_exists():
    """Inserting a child with a valid parent must succeed."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)

    conn.execute(
        "INSERT INTO agents (id, name, status, last_seen_time) VALUES ('a1', 'test', 'active', 0)"
    )
    conn.execute(
        "INSERT INTO sessions (id, agent_id, status, time_created, time_updated) "
        "VALUES ('s_ok', 'a1', 'active', 0, 0)"
    )
    conn.commit()

    row = conn.execute("SELECT id FROM sessions WHERE id = 's_ok'").fetchone()
    assert row is not None
    conn.close()
