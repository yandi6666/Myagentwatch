# 2026-06-28 Chat v4 Channel Collaboration

作者：Codex  
用户：天宇

## Summary

实现 MyAgentWatch Chat v4 的 Mattermost-like 协作消息层。v4 不改变 v3 的执行入口：`agent_tasks` 仍是执行队列，inbox 仍是通知/审计层；本次重点是频道成员、参与者视角未读、结构化提及、消息上下文和任务卡片展示。

## Changes

- 数据库 schema 升级到 v10。
- 新增 `chat_conversation_members`：
  - conversation + participant 级成员关系。
  - 记录 role、muted、last_seen_message_id、unread_count、mention_count。
- 新增 `chat_message_mentions`：
  - 结构化保存 `@agent` / `@all` 提及。
  - 支持按 Agent 查询未读提及。
- `GET /api/chat/conversations` 支持：
  - `participant_type`
  - `participant_id`
  - 按参与者视角返回 unread、mention、pending task 数。
- 新增 API：
  - `GET /api/chat/mentions`
  - `GET /api/chat/messages/<message_id>/context`
- `query_chat_thread` 增加线程摘要：
  - reply_count
  - last_reply_at
  - participants
- 消息返回中增加关联 `agent_tasks` task card。
- 发送消息后会更新频道成员未读/提及状态。
- 普通群聊仍不进入 Agent inbox，也不创建 `agent_tasks`。
- `@Agent` 和私聊仍按 v3 规则创建 inbox + task。
- CLI 新增：
  - `myaw mentions`
  - `myaw context <msg_id>`
- `myaw conversations` 显示 unread / mention / pending task。
- 前端最小增强：
  - 会话列表显示未读、提及、task 数。
  - 消息气泡显示 thread hint 和 task card。
  - inbox 点击跳到原会话并高亮来源消息。

## Validation

已通过：

```powershell
python -m py_compile myagentwatch\db.py myagentwatch\queries.py routes\chat_api.py routes\agent_tasks_api.py app.py
python tests\test_smoke.py
python -m py_compile myagentwatch_cli\cli.py myagentwatch_cli\daemon.py myagentwatch_cli\client.py
python -m myagentwatch_cli.cli mentions --help
python -m myagentwatch_cli.cli context --help
```

Smoke tests：

```text
11/11 passed
```

## Notes

- v4 仍然不引入新的 WebSocket 协议；前端继续使用现有 Socket.IO 消息事件。
- v4 不启用 Agent 自动执行；自动启动 Agent CLI 仍留给后续 v4.1/v5。
- 运行中的 MyAgentWatch 服务端和 CLI daemon 需要重启后才会加载新代码。
