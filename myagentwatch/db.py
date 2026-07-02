"""MyAgentWatch internal SQLite database management."""

import contextlib
import os
import sqlite3
import time
from collections.abc import Generator
from pathlib import Path

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "myagentwatch.db"
)

_pragma_ensured = False
BUSY_RETRY_MAX = 3
BUSY_RETRY_DELAY = 0.05

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    db_path TEXT NOT NULL,
    log_dir TEXT,
    enabled INTEGER DEFAULT 1,
    last_sync_time INTEGER,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT,
    source_id INTEGER REFERENCES data_sources(id),
    group_name TEXT,
    agent_type TEXT,
    model_id TEXT,
    provider_id TEXT,
    status TEXT DEFAULT 'inactive',
    last_seen_time INTEGER,
    last_heartbeat_at INTEGER DEFAULT 0,
    status_since INTEGER DEFAULT 0,
    metadata TEXT,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES agents(id),
    title TEXT,
    slug TEXT,
    directory TEXT,
    status TEXT,
    parent_id TEXT,
    message_count INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0,
    total_tokens_input INTEGER DEFAULT 0,
    total_tokens_output INTEGER DEFAULT 0,
    total_tokens_reasoning INTEGER DEFAULT 0,
    total_cache_read INTEGER DEFAULT 0,
    total_cache_write INTEGER DEFAULT 0,
    time_created INTEGER,
    time_updated INTEGER
);

CREATE TABLE IF NOT EXISTS token_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    agent_id TEXT,
    message_id TEXT,
    part_id TEXT,
    model_id TEXT,
    provider_id TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_reasoning INTEGER,
    cache_read INTEGER,
    cache_write INTEGER,
    cost REAL,
    timestamp INTEGER
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    agent_id TEXT,
    message_id TEXT,
    part_id TEXT,
    tool_name TEXT,
    call_id TEXT,
    status TEXT,
    description TEXT,
    exit_code INTEGER,
    duration_ms INTEGER,
    error_output TEXT,
    timestamp INTEGER
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    agent_id TEXT,
    event_type TEXT,
    data TEXT,
    severity TEXT DEFAULT 'info',
    timestamp INTEGER
);

CREATE TABLE IF NOT EXISTS health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER,
    metric TEXT,
    value REAL,
    unit TEXT,
    timestamp INTEGER
);

CREATE TABLE IF NOT EXISTS agent_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    cpu_pct REAL,
    memory_pct REAL,
    memory_used_mb REAL,
    memory_total_mb REAL,
    disk_pct REAL,
    disk_used_gb REAL,
    disk_total_gb REAL,
    gpu_pct REAL,
    gpu_memory_used_mb REAL,
    net_sent_bytes INTEGER,
    net_recv_bytes INTEGER,
    timestamp INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    pid INTEGER,
    process_name TEXT NOT NULL,
    cmdline TEXT DEFAULT '',
    status TEXT DEFAULT '',
    cpu_pct REAL,
    memory_mb REAL,
    detected_role TEXT DEFAULT '',
    timestamp INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_resources_agent
    ON agent_resources(agent_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_agent_processes_agent
    ON agent_processes(agent_id, timestamp);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    date TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    tokens_reasoning INTEGER,
    cache_read INTEGER,
    cache_write INTEGER,
    total_cost REAL,
    message_count INTEGER,
    tool_call_count INTEGER,
    success_count INTEGER,
    error_count INTEGER
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT,
    agent_id TEXT,
    level TEXT,
    message TEXT,
    is_active INTEGER DEFAULT 1,
    created_at INTEGER,
    resolved_at INTEGER
);

CREATE TABLE IF NOT EXISTS agent_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_agent_id TEXT NOT NULL,
    target_agent_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    call_count INTEGER DEFAULT 1,
    last_seen INTEGER,
    UNIQUE(source_agent_id, target_agent_id, relation_type)
);

CREATE TABLE IF NOT EXISTS template_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT UNIQUE NOT NULL,
    config_json TEXT NOT NULL,
    active INTEGER DEFAULT 0,
    applied_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_token_records_ts ON token_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_token_records_session ON token_records(session_id);
CREATE INDEX IF NOT EXISTS idx_token_records_agent ON token_records(agent_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_session ON activity_log(session_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_ts ON activity_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_health_checks_ts ON health_checks(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(is_active);
CREATE UNIQUE INDEX IF NOT EXISTS idx_data_sources_name ON data_sources(name);

-- ── 对话日志系统 ──

CREATE TABLE IF NOT EXISTS conversation_turns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    natural_key     TEXT NOT NULL UNIQUE,
    agent_id        TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    trace_id        TEXT,
    seq             INTEGER NOT NULL,
    phase           TEXT NOT NULL,
    role            TEXT NOT NULL,
    handoff_id      INTEGER,
    source_type     TEXT NOT NULL,
    severity        TEXT DEFAULT 'info',
    token_count     INTEGER DEFAULT 0,
    duration_ms     INTEGER DEFAULT 0,
    time_start      INTEGER NOT NULL,
    time_end        INTEGER
);

CREATE TABLE IF NOT EXISTS turn_content (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id         INTEGER NOT NULL REFERENCES conversation_turns(id) ON DELETE CASCADE,
    block_type      TEXT NOT NULL,
    content         TEXT NOT NULL,
    tool_name       TEXT,
    tool_call_id    TEXT,
    mime_type       TEXT DEFAULT 'text/plain',
    char_count      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_handoffs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    trace_id        TEXT,
    from_agent_id   TEXT NOT NULL,
    to_agent_id     TEXT NOT NULL,
    from_turn_id    INTEGER REFERENCES conversation_turns(id),
    to_session_id   TEXT,
    prompt_text     TEXT,
    result_text     TEXT,
    subagent_type   TEXT,
    status          TEXT DEFAULT 'pending',
    time_start      INTEGER NOT NULL,
    time_end        INTEGER
);

CREATE TABLE IF NOT EXISTS tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    description       TEXT DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'queued',
    assigned_agent_id TEXT DEFAULT '',
    parent_task_id    INTEGER REFERENCES tasks(id),
    session_id        TEXT DEFAULT '',
    priority          INTEGER DEFAULT 0,
    tags              TEXT DEFAULT '',
    source_handoff_id INTEGER UNIQUE,
    time_created      INTEGER NOT NULL,
    time_started      INTEGER,
    time_completed    INTEGER,
    updated_at        INTEGER NOT NULL,
    metadata          TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS task_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    status      TEXT,
    actor_id    TEXT DEFAULT '',
    message     TEXT DEFAULT '',
    timestamp   INTEGER NOT NULL,
    metadata    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS collector_progress (
    source_name     TEXT PRIMARY KEY,
    file_path       TEXT NOT NULL,
    byte_offset     INTEGER DEFAULT 0,
    last_turn_seq   INTEGER DEFAULT 0,
    updated_at      INTEGER NOT NULL
);

-- 索引

CREATE INDEX IF NOT EXISTS idx_turns_agent
    ON conversation_turns(agent_id, time_start);
CREATE INDEX IF NOT EXISTS idx_turns_session
    ON conversation_turns(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_turns_phase
    ON conversation_turns(phase, time_start);
CREATE INDEX IF NOT EXISTS idx_turns_time
    ON conversation_turns(time_start);
CREATE INDEX IF NOT EXISTS idx_turns_trace
    ON conversation_turns(trace_id);
CREATE INDEX IF NOT EXISTS idx_turns_severity
    ON conversation_turns(severity, time_start);

CREATE INDEX IF NOT EXISTS idx_content_turn
    ON turn_content(turn_id, block_type);
CREATE INDEX IF NOT EXISTS idx_content_tool
    ON turn_content(tool_name) WHERE tool_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_handoffs_from
    ON agent_handoffs(from_agent_id, time_start);
CREATE INDEX IF NOT EXISTS idx_handoffs_to
    ON agent_handoffs(to_agent_id, time_start);
CREATE INDEX IF NOT EXISTS idx_handoffs_session
    ON agent_handoffs(session_id);

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_tasks_agent
    ON tasks(assigned_agent_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_tasks_session
    ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_task_records_task
    ON task_records(task_id, timestamp);

-- 全文搜索

CREATE VIRTUAL TABLE IF NOT EXISTS turn_content_fts USING fts5(
    content,
    tool_name,
    content='turn_content',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS turn_content_ai
    AFTER INSERT ON turn_content
BEGIN
    INSERT INTO turn_content_fts(rowid, content, tool_name)
    VALUES (new.id, new.content, COALESCE(new.tool_name, ''));
END;

CREATE TRIGGER IF NOT EXISTS turn_content_ad
    AFTER DELETE ON turn_content
BEGIN
    INSERT INTO turn_content_fts(turn_content_fts, rowid, content, tool_name)
    VALUES ('delete', old.id, old.content, COALESCE(old.tool_name, ''));
END;

CREATE TRIGGER IF NOT EXISTS turn_content_au
    AFTER UPDATE ON turn_content
BEGIN
    INSERT INTO turn_content_fts(turn_content_fts, rowid, content, tool_name)
    VALUES ('delete', old.id, old.content, COALESCE(old.tool_name, ''));
    INSERT INTO turn_content_fts(rowid, content, tool_name)
    VALUES (new.id, new.content, COALESCE(new.tool_name, ''));
END;

-- ── 即时通讯系统 ──

CREATE TABLE IF NOT EXISTS chat_conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT NOT NULL DEFAULT 'group',
    agent_id        TEXT,
    title           TEXT,
    last_message    TEXT,
    last_time       INTEGER,
    unread_count    INTEGER DEFAULT 0,
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    sender_type     TEXT NOT NULL DEFAULT 'human',
    sender_id       TEXT,
    sender_name     TEXT NOT NULL,
    content         TEXT NOT NULL,
    msg_type        TEXT DEFAULT 'text',
    reply_to        INTEGER,
    root_id         INTEGER,
    metadata_json   TEXT DEFAULT '{}',
    priority        TEXT DEFAULT '',
    edited_at       INTEGER,
    deleted_at      INTEGER,
    is_agent_initiated INTEGER DEFAULT 0,
    task_context    TEXT DEFAULT '',
    share_type      TEXT DEFAULT 'none',
    timestamp       INTEGER NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
);

CREATE TABLE IF NOT EXISTS chat_attachments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      INTEGER NOT NULL,
    attachment_type TEXT NOT NULL DEFAULT 'file',
    url             TEXT DEFAULT '',
    title           TEXT DEFAULT '',
    mime_type       TEXT DEFAULT '',
    size_bytes      INTEGER,
    metadata_json   TEXT DEFAULT '{}',
    created_at      INTEGER NOT NULL,
    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_conversation_state (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id      INTEGER NOT NULL,
    participant_type     TEXT NOT NULL DEFAULT 'agent',
    participant_id       TEXT NOT NULL,
    last_seen_message_id INTEGER DEFAULT 0,
    unread_count         INTEGER DEFAULT 0,
    mention_count        INTEGER DEFAULT 0,
    urgent_count         INTEGER DEFAULT 0,
    updated_at           INTEGER NOT NULL,
    UNIQUE(conversation_id, participant_type, participant_id),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_chat_msgs_conv ON chat_messages(conversation_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_chat_msgs_time ON chat_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_chat_conv_type ON chat_conversations(type);
CREATE INDEX IF NOT EXISTS idx_chat_attach_msg ON chat_attachments(message_id);
CREATE INDEX IF NOT EXISTS idx_chat_state_participant ON chat_conversation_state(participant_type, participant_id);
CREATE INDEX IF NOT EXISTS idx_chat_state_conv ON chat_conversation_state(conversation_id);

CREATE TABLE IF NOT EXISTS chat_conversation_members (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id      INTEGER NOT NULL,
    participant_type     TEXT NOT NULL DEFAULT 'human',
    participant_id       TEXT NOT NULL,
    display_name         TEXT DEFAULT '',
    role                 TEXT DEFAULT 'member',
    muted                INTEGER DEFAULT 0,
    last_seen_message_id INTEGER DEFAULT 0,
    unread_count         INTEGER DEFAULT 0,
    mention_count        INTEGER DEFAULT 0,
    task_count           INTEGER DEFAULT 0,
    joined_at            INTEGER NOT NULL,
    updated_at           INTEGER NOT NULL,
    UNIQUE(conversation_id, participant_type, participant_id),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
);

CREATE TABLE IF NOT EXISTS chat_message_mentions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id       INTEGER NOT NULL,
    conversation_id  INTEGER NOT NULL,
    participant_type TEXT NOT NULL DEFAULT 'agent',
    participant_id   TEXT NOT NULL,
    mention_token    TEXT DEFAULT '',
    mention_type     TEXT NOT NULL DEFAULT 'direct',
    is_read          INTEGER DEFAULT 0,
    created_at       INTEGER NOT NULL,
    UNIQUE(message_id, participant_type, participant_id, mention_type),
    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_chat_members_participant ON chat_conversation_members(participant_type, participant_id);
CREATE INDEX IF NOT EXISTS idx_chat_members_conv ON chat_conversation_members(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_mentions_participant ON chat_message_mentions(participant_type, participant_id, is_read, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_mentions_message ON chat_message_mentions(message_id);

CREATE TABLE IF NOT EXISTS agent_task_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id        INTEGER NOT NULL,
    event_type     TEXT NOT NULL,
    actor_id       TEXT DEFAULT '',
    message        TEXT DEFAULT '',
    data_json      TEXT DEFAULT '{}',
    created_at     INTEGER NOT NULL,
    FOREIGN KEY (task_id) REFERENCES agent_tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_agent_task_events_task ON agent_task_events(task_id, created_at);
"""


def get_db_path() -> str:
    return DB_PATH


SCHEMA_VERSION = 12

MIGRATIONS = {
    1: [
        "ALTER TABLE agents ADD COLUMN last_heartbeat_at INTEGER DEFAULT 0",
        "ALTER TABLE agents ADD COLUMN status_since INTEGER DEFAULT 0",
    ],
    2: [
        "CREATE TABLE IF NOT EXISTS pricing ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  provider_id TEXT NOT NULL,"
        "  model_id TEXT NOT NULL,"
        "  display_name TEXT NOT NULL,"
        "  price_per_1m_input REAL NOT NULL,"
        "  price_per_1m_output REAL NOT NULL,"
        "  price_per_1m_cache_read REAL DEFAULT 0,"
        "  price_per_1m_cache_write REAL DEFAULT 0,"
        "  currency TEXT DEFAULT 'USD',"
        "  is_active INTEGER DEFAULT 1,"
        "  created_at INTEGER,"
        "  UNIQUE(provider_id, model_id)"
        ")",
    ],
    3: [
        "ALTER TABLE chat_messages ADD COLUMN is_agent_initiated INTEGER DEFAULT 0",
        "ALTER TABLE chat_messages ADD COLUMN task_context TEXT DEFAULT ''",
        "ALTER TABLE chat_messages ADD COLUMN share_type TEXT DEFAULT 'none'",
        "CREATE TABLE IF NOT EXISTS friend_requests ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  from_agent_id TEXT NOT NULL,"
        "  to_agent_id TEXT,"
        "  from_agent_name TEXT NOT NULL,"
        "  message TEXT DEFAULT '',"
        "  status TEXT DEFAULT 'pending',"
        "  created_at INTEGER NOT NULL,"
        "  resolved_at INTEGER"
        ")",
    ],
    4: [
        "CREATE TABLE IF NOT EXISTS inbox ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  recipient_type TEXT NOT NULL DEFAULT 'human',"
        "  recipient_id TEXT DEFAULT '',"
        "  type TEXT NOT NULL DEFAULT 'system',"
        "  severity TEXT DEFAULT 'info',"
        "  title TEXT NOT NULL,"
        "  body TEXT DEFAULT '',"
        "  link TEXT DEFAULT '',"
        "  source_agent_id TEXT DEFAULT '',"
        "  is_read INTEGER DEFAULT 0,"
        "  is_archived INTEGER DEFAULT 0,"
        "  created_at INTEGER NOT NULL"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_inbox_recipient ON inbox(recipient_type, recipient_id, is_read)",
        "CREATE INDEX IF NOT EXISTS idx_inbox_time ON inbox(created_at DESC)",
    ],
    5: [
        "CREATE TABLE IF NOT EXISTS users ("
        "  id TEXT PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  type TEXT NOT NULL DEFAULT 'human' CHECK (type IN ('human', 'agent')),"
        "  avatar_url TEXT,"
        "  token_hash TEXT UNIQUE,"
        "  token_prefix TEXT,"
        "  token_created_at INTEGER,"
        "  created_at INTEGER NOT NULL"
        ")",
    ],
    6: [
        "CREATE TABLE IF NOT EXISTS tasks ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  title TEXT NOT NULL,"
        "  description TEXT DEFAULT '',"
        "  status TEXT NOT NULL DEFAULT 'queued',"
        "  assigned_agent_id TEXT DEFAULT '',"
        "  parent_task_id INTEGER REFERENCES tasks(id),"
        "  session_id TEXT DEFAULT '',"
        "  priority INTEGER DEFAULT 0,"
        "  tags TEXT DEFAULT '',"
        "  source_handoff_id INTEGER UNIQUE,"
        "  time_created INTEGER NOT NULL,"
        "  time_started INTEGER,"
        "  time_completed INTEGER,"
        "  updated_at INTEGER NOT NULL,"
        "  metadata TEXT DEFAULT '{}'"
        ")",
        "CREATE TABLE IF NOT EXISTS task_records ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,"
        "  event_type TEXT NOT NULL,"
        "  status TEXT,"
        "  actor_id TEXT DEFAULT '',"
        "  message TEXT DEFAULT '',"
        "  timestamp INTEGER NOT NULL,"
        "  metadata TEXT DEFAULT '{}'"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(assigned_agent_id, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_task_records_task ON task_records(task_id, timestamp)",
    ],
    7: [
        "CREATE TABLE IF NOT EXISTS agent_resources ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  agent_id TEXT NOT NULL,"
        "  cpu_pct REAL,"
        "  memory_pct REAL,"
        "  memory_used_mb REAL,"
        "  memory_total_mb REAL,"
        "  disk_pct REAL,"
        "  disk_used_gb REAL,"
        "  disk_total_gb REAL,"
        "  gpu_pct REAL,"
        "  gpu_memory_used_mb REAL,"
        "  net_sent_bytes INTEGER,"
        "  net_recv_bytes INTEGER,"
        "  timestamp INTEGER NOT NULL"
        ")",
        "CREATE TABLE IF NOT EXISTS agent_processes ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  agent_id TEXT NOT NULL,"
        "  pid INTEGER,"
        "  process_name TEXT NOT NULL,"
        "  cmdline TEXT DEFAULT '',"
        "  status TEXT DEFAULT '',"
        "  cpu_pct REAL,"
        "  memory_mb REAL,"
        "  detected_role TEXT DEFAULT '',"
        "  timestamp INTEGER NOT NULL"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_agent_resources_agent ON agent_resources(agent_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_agent_processes_agent ON agent_processes(agent_id, timestamp)",
    ],
    8: [
        "ALTER TABLE chat_messages ADD COLUMN root_id INTEGER",
        "ALTER TABLE chat_messages ADD COLUMN metadata_json TEXT DEFAULT '{}'",
        "ALTER TABLE chat_messages ADD COLUMN priority TEXT DEFAULT ''",
        "ALTER TABLE chat_messages ADD COLUMN edited_at INTEGER",
        "ALTER TABLE chat_messages ADD COLUMN deleted_at INTEGER",
        "CREATE TABLE IF NOT EXISTS chat_attachments ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  message_id INTEGER NOT NULL,"
        "  attachment_type TEXT NOT NULL DEFAULT 'file',"
        "  url TEXT DEFAULT '',"
        "  title TEXT DEFAULT '',"
        "  mime_type TEXT DEFAULT '',"
        "  size_bytes INTEGER,"
        "  metadata_json TEXT DEFAULT '{}',"
        "  created_at INTEGER NOT NULL,"
        "  FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE"
        ")",
        "CREATE TABLE IF NOT EXISTS chat_conversation_state ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  conversation_id INTEGER NOT NULL,"
        "  participant_type TEXT NOT NULL DEFAULT 'agent',"
        "  participant_id TEXT NOT NULL,"
        "  last_seen_message_id INTEGER DEFAULT 0,"
        "  unread_count INTEGER DEFAULT 0,"
        "  mention_count INTEGER DEFAULT 0,"
        "  urgent_count INTEGER DEFAULT 0,"
        "  updated_at INTEGER NOT NULL,"
        "  UNIQUE(conversation_id, participant_type, participant_id),"
        "  FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_chat_msgs_root ON chat_messages(root_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_chat_attach_msg ON chat_attachments(message_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_state_participant ON chat_conversation_state(participant_type, participant_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_state_conv ON chat_conversation_state(conversation_id)",
        "ALTER TABLE inbox ADD COLUMN source_conversation_id INTEGER",
        "ALTER TABLE inbox ADD COLUMN source_message_id INTEGER",
        "ALTER TABLE inbox ADD COLUMN delivery_type TEXT DEFAULT ''",
        "ALTER TABLE inbox ADD COLUMN source_title TEXT DEFAULT ''",
        "ALTER TABLE inbox ADD COLUMN metadata_json TEXT DEFAULT '{}'",
        "CREATE INDEX IF NOT EXISTS idx_inbox_source ON inbox(source_conversation_id, source_message_id)",
    ],
    9: [
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user-member'",
        "ALTER TABLE users ADD COLUMN permissions_json TEXT DEFAULT '{}'",
        "ALTER TABLE users ADD COLUMN permission_limits_json TEXT DEFAULT '{}'",
        "ALTER TABLE agents ADD COLUMN role TEXT DEFAULT 'agent-worker'",
        "ALTER TABLE agents ADD COLUMN permissions_json TEXT DEFAULT '{}'",
        "CREATE TABLE IF NOT EXISTS agent_tasks ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  agent_id TEXT NOT NULL,"
        "  agent_name TEXT DEFAULT '',"
        "  agent_role TEXT DEFAULT 'agent-worker',"
        "  requester_type TEXT DEFAULT 'user',"
        "  requester_id TEXT DEFAULT '',"
        "  requester_name TEXT DEFAULT '',"
        "  requester_role TEXT DEFAULT 'user-member',"
        "  task_type TEXT NOT NULL DEFAULT 'reply',"
        "  status TEXT NOT NULL DEFAULT 'queued',"
        "  priority INTEGER DEFAULT 0,"
        "  title TEXT DEFAULT '',"
        "  body TEXT DEFAULT '',"
        "  source_conversation_id INTEGER,"
        "  source_message_id INTEGER,"
        "  source_title TEXT DEFAULT '',"
        "  required_capability TEXT DEFAULT 'can_request_agent_reply',"
        "  required_capabilities_json TEXT DEFAULT '[]',"
        "  allow_autostart INTEGER DEFAULT 0,"
        "  autostart_denied_reason TEXT DEFAULT '',"
        "  claimed_by TEXT DEFAULT '',"
        "  claimed_at INTEGER,"
        "  started_at INTEGER,"
        "  completed_at INTEGER,"
        "  result_text TEXT DEFAULT '',"
        "  error_text TEXT DEFAULT '',"
        "  metadata_json TEXT DEFAULT '{}',"
        "  created_at INTEGER NOT NULL,"
        "  updated_at INTEGER NOT NULL"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent_status ON agent_tasks(agent_id, status, priority, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_source ON agent_tasks(source_conversation_id, source_message_id)",
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status, updated_at)",
    ],
    10: [
        "CREATE TABLE IF NOT EXISTS chat_conversation_members ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  conversation_id INTEGER NOT NULL,"
        "  participant_type TEXT NOT NULL DEFAULT 'human',"
        "  participant_id TEXT NOT NULL,"
        "  display_name TEXT DEFAULT '',"
        "  role TEXT DEFAULT 'member',"
        "  muted INTEGER DEFAULT 0,"
        "  last_seen_message_id INTEGER DEFAULT 0,"
        "  unread_count INTEGER DEFAULT 0,"
        "  mention_count INTEGER DEFAULT 0,"
        "  task_count INTEGER DEFAULT 0,"
        "  joined_at INTEGER NOT NULL,"
        "  updated_at INTEGER NOT NULL,"
        "  UNIQUE(conversation_id, participant_type, participant_id),"
        "  FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)"
        ")",
        "CREATE TABLE IF NOT EXISTS chat_message_mentions ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  message_id INTEGER NOT NULL,"
        "  conversation_id INTEGER NOT NULL,"
        "  participant_type TEXT NOT NULL DEFAULT 'agent',"
        "  participant_id TEXT NOT NULL,"
        "  mention_token TEXT DEFAULT '',"
        "  mention_type TEXT NOT NULL DEFAULT 'direct',"
        "  is_read INTEGER DEFAULT 0,"
        "  created_at INTEGER NOT NULL,"
        "  UNIQUE(message_id, participant_type, participant_id, mention_type),"
        "  FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,"
        "  FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_chat_members_participant ON chat_conversation_members(participant_type, participant_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_members_conv ON chat_conversation_members(conversation_id)",
        "CREATE INDEX IF NOT EXISTS idx_chat_mentions_participant ON chat_message_mentions(participant_type, participant_id, is_read, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_chat_mentions_message ON chat_message_mentions(message_id)",
    ],
    11: [
        "ALTER TABLE agent_tasks ADD COLUMN lease_expires_at INTEGER",
        "ALTER TABLE agent_tasks ADD COLUMN attempt_count INTEGER DEFAULT 0",
        "ALTER TABLE agent_tasks ADD COLUMN max_attempts INTEGER DEFAULT 3",
        "ALTER TABLE agent_tasks ADD COLUMN last_error TEXT DEFAULT ''",
        "CREATE TABLE IF NOT EXISTS agent_task_events ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  task_id INTEGER NOT NULL,"
        "  event_type TEXT NOT NULL,"
        "  actor_id TEXT DEFAULT '',"
        "  message TEXT DEFAULT '',"
        "  data_json TEXT DEFAULT '{}',"
        "  created_at INTEGER NOT NULL,"
        "  FOREIGN KEY (task_id) REFERENCES agent_tasks(id) ON DELETE CASCADE"
        ")",
        "CREATE INDEX IF NOT EXISTS idx_agent_task_events_task ON agent_task_events(task_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_lease ON agent_tasks(status, lease_expires_at)",
    ],
    12: [
        "ALTER TABLE agent_tasks ADD COLUMN approval_status TEXT DEFAULT 'not_required'",
        "ALTER TABLE agent_tasks ADD COLUMN approval_required INTEGER DEFAULT 0",
        "ALTER TABLE agent_tasks ADD COLUMN approved_by TEXT DEFAULT ''",
        "ALTER TABLE agent_tasks ADD COLUMN approved_at INTEGER",
        "ALTER TABLE agent_tasks ADD COLUMN rejected_by TEXT DEFAULT ''",
        "ALTER TABLE agent_tasks ADD COLUMN rejected_at INTEGER",
        "ALTER TABLE agent_tasks ADD COLUMN rejected_reason TEXT DEFAULT ''",
        "UPDATE agent_tasks SET approval_required = CASE WHEN task_type = 'reply' THEN 0 ELSE 1 END",
        "UPDATE agent_tasks SET approval_status = CASE WHEN task_type = 'reply' THEN 'not_required' ELSE 'pending' END "
        "WHERE approval_status IS NULL OR approval_status = '' OR approval_status = 'not_required'",
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_approval ON agent_tasks(approval_status, approval_required, status)",
    ],
}


def _current_schema_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version INTEGER PRIMARY KEY,"
        "  applied_at INTEGER NOT NULL"
        ")"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] if row[0] is not None else 0


def _apply_migrations(conn: sqlite3.Connection):
    current = _current_schema_version(conn)
    for version in sorted(MIGRATIONS):
        if version <= current:
            continue
        for sql in MIGRATIONS[version]:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (version, int(time.time() * 1000)),
        )
    if current < max(MIGRATIONS.keys(), default=0):
        conn.commit()


def init_db() -> None:
    """Initialize the MyAgentWatch database, creating tables if needed."""
    db_dir = os.path.dirname(DB_PATH)
    Path(db_dir).mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _apply_migrations(conn)

    from myagentwatch.pricing import seed_pricing
    seeded = seed_pricing(conn)
    if seeded:
        conn.commit()

    # Seed default human user
    now_ms = int(time.time() * 1000)
    conn.execute(
        "INSERT OR IGNORE INTO users (id, name, type, created_at) VALUES (?, ?, ?, ?)",
        ("tianyu", "天宇", "human", now_ms),
    )
    conn.execute(
        "UPDATE users SET role = 'user-owner' WHERE id IN ('tianyu', '天宇') OR name = '天宇'"
    )
    # Seed agent users from existing agents
    for row in conn.execute("SELECT id, name FROM agents WHERE status != 'removed'").fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO users (id, name, type, created_at) VALUES (?, ?, 'agent', ?)",
            (row[0], row[1], now_ms),
        )
    conn.execute(
        "UPDATE agents SET role = 'agent-root' "
        "WHERE id = 'codex:codex:codex' OR lower(name) = 'codex'"
    )
    if seeded:
        pass  # commit already applied above if pricing was newly seeded

    conn.commit()
    conn.close()


def get_connection() -> sqlite3.Connection:
    """Get a read/write connection to the MyAgentWatch database.

    Uses WAL journal mode for concurrent read/write. journal_mode is persistent
    (set once), foreign_keys is per-connection (set every time).
    """
    global _pragma_ensured
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    if not _pragma_ensured:
        conn.execute("PRAGMA journal_mode=WAL")
        _pragma_ensured = True
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.contextmanager
def database() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a DB connection and ensures it's closed."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def execute_with_retry(conn, sql, params=(), max_retries=BUSY_RETRY_MAX):
    """Execute SQL with retry on SQLITE_BUSY. Use for write operations."""
    for attempt in range(max_retries):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(BUSY_RETRY_DELAY * (attempt + 1))
                continue
            raise
