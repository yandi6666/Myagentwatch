"""MyAgentWatch — User & PAT token management (inspired by Multica).

PAT format: myaw_<40 hex chars>  (Multica uses mul_ prefix)
Stored as SHA-256 hash in users.token_hash. Only the prefix is shown in UI.
"""

import hashlib
import os
import time


def generate_pat() -> tuple[str, str, str]:
    """Generate a PAT. Returns (full_token, token_hash, token_prefix)."""
    raw = os.urandom(20)
    token = "myaw_" + raw.hex()
    h = hashlib.sha256(token.encode()).hexdigest()
    prefix = token[:10]  # "myaw_xxxxx"
    return token, h, prefix


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_pat_for(conn, user_id: str) -> str | None:
    """Issue a new PAT for a user. Returns the full token (show once)."""
    token, h, prefix = generate_pat()
    now_ms = int(time.time() * 1000)
    from myagentwatch.db import execute_with_retry
    execute_with_retry(conn,
        "UPDATE users SET token_hash = ?, token_prefix = ?, token_created_at = ? WHERE id = ?",
        (h, prefix, now_ms, user_id),
    )
    conn.commit()
    return token


def verify_token(conn, token: str) -> dict | None:
    """Verify a PAT. Returns user row dict if valid, None otherwise."""
    if not token or not token.startswith("myaw_"):
        return None
    h = hash_token(token)
    row = conn.execute(
        "SELECT id, name, type, token_hash, token_prefix, token_created_at, created_at "
        "FROM users WHERE token_hash = ?",
        (h,),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def list_users(conn):
    rows = conn.execute(
        "SELECT id, name, type, token_prefix, token_created_at, created_at FROM users ORDER BY type, name"
    ).fetchall()
    return [dict(r) for r in rows]
