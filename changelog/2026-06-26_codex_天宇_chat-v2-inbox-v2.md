# 2026-06-26 Codex / 天宇：Chat v2 与 Agent Inbox v2

## 背景

本次修改基于“吸收 Mattermost 成熟协作模型，但不照搬 Mattermost 代码”的方向，先升级 MyAgentWatch 的群聊/私聊消息底座，再为 Agent Inbox v2 提供稳定的结构化来源信息。

核心目标：让消息本体、线程、附件、未读状态、inbox 投递分层，避免后续 UI 和 CLI 继续依赖 `chat:1:msg:54` 这类纯文本定位。

## 服务端改动

- `myagentwatch/db.py`
  - `SCHEMA_VERSION` 升级到 `8`。
  - `chat_messages` 新增 `root_id`、`metadata_json`、`priority`、`edited_at`、`deleted_at`。
  - 新增 `chat_attachments`，支持链接型图片、文件、视频、音频、URL 附件元数据。
  - 新增 `chat_conversation_state`，为后续按 agent/user + conversation 记录已读位置、未读数、提及数、紧急数提供底座。
  - `inbox` 新增 `source_conversation_id`、`source_message_id`、`delivery_type`、`source_title`、`metadata_json`。

- `myagentwatch/queries.py`
  - 新增消息附件 hydrate。
  - 新增 `query_chat_message`、`query_chat_thread`。
  - `insert_chat_message` 支持 `reply_to/root_id/attachments/metadata/priority`。
  - 新增 `upsert_chat_conversation_state`。

- `routes/api.py`
  - `_create_inbox_item` 支持结构化 inbox 字段。
  - 旧调用保持兼容。

- `routes/chat_api.py`
  - 保留原有会话和消息接口。
  - 新增 `GET /api/chat/messages/<msg_id>/thread`。
  - `POST /api/chat/messages/<conv_id>` 支持线程、附件、metadata、priority。
  - 群聊 `@codex` / `@agent_id`、私聊 Agent 时，会投递结构化 Agent inbox。

## CLI 改动

- `myagentwatch_cli/local_inbox.py`
  - 新增 `find_inbox_item`。
  - 新增 `max_chat_ids`，支持 daemon 多会话恢复同步位置。

- `myagentwatch_cli/daemon.py`
  - daemon 从只同步默认 `conv_id=1` 升级为拉取会话列表并逐个会话增量同步。
  - 状态中新增 `last_chat_message_ids`、`chat_conversation_count`。

- `myagentwatch_cli/cli.py`
  - 新增 `myaw thread <msg_id>`。
  - 新增 `myaw reply <msg_id> "message"`。
  - 新增 `myaw inbox reply <inbox_id> "message"`。
  - `myaw inbox` 改为结构化显示：来源、类型、优先级、发件人、消息、附件、位置。

## 验证

已完成：

```text
python -m py_compile myagentwatch\db.py myagentwatch\queries.py routes\api.py routes\chat_api.py tests\test_smoke.py
python -m py_compile myagentwatch_cli\cli.py myagentwatch_cli\daemon.py myagentwatch_cli\local_inbox.py
python tests\test_smoke.py
```

结果：

```text
8/8 passed
```

数据库已实际迁移到 schema v8，并确认：

```text
chat_messages.root_id 存在
inbox.source_conversation_id 存在
```

## 注意事项

- 当前磁盘代码和数据库 schema 已更新。
- 运行中的 MyAgentWatch 服务进程和 `myaw daemon` 尚未重启。
- 因此新 API/daemon 多会话同步逻辑需要重启后才会被运行时加载。

## 下一步建议

1. 重启 MyAgentWatch 服务。
2. 重启 `myaw daemon`。
3. 做 live 验证：
   - 普通群聊消息不进 Agent inbox。
   - `@codex` 群聊消息进入 Agent inbox，并带 `source_conversation_id/source_message_id`。
   - `myaw thread <msg_id>` 能显示线程。
   - `myaw reply <msg_id> "..."` 能回复具体消息。
   - `myaw inbox reply <id> "..."` 能从 inbox 直接回复来源消息并标记已读。
