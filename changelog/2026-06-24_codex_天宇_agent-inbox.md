# MyAgentWatch 维护日志 — 2026-06-24

**Agent：Codex**  
**用户：天宇**  
**主题：myagentwatch-cli 后台消息监听与 Agent Inbox**

## 背景

天宇提出当前 `myaw chat` 需要 Agent 手动运行，导致 Agent 如果不主动拉取群聊，就无法知道人类是否发了消息。

本次目标是让 `myaw daemon` 成为 Agent 端常驻消息监听器，后台同步 MyAgentWatch 群聊、私聊和 inbox，并在本地保存未读状态。

## 处理内容

### 服务端接口增强

修改 MyAgentWatch 服务端：

```text
routes\api.py
routes\chat_api.py
myagentwatch\queries.py
```

完成内容：

- `GET /api/chat/messages/<conv_id>?after_id=<id>&limit=<n>` 支持按消息 ID 增量拉取新消息。
- `_create_inbox_item` 调整为 `routes.api` 顶层函数，方便 chat/alerting 复用。
- 人类发送群聊消息时，如果内容包含 `@agent_id`、`@agent_name` 或 `@display_name`，会投递到对应 Agent 的 inbox。
- 私聊 Agent 时，消息会投递到目标 Agent 的 inbox。
- 保留现有 `/api/inbox?recipient=<id>` 查询能力。

### CLI 新增能力

修改 myagentwatch-cli：

```text
myagentwatch_cli\cli.py
myagentwatch_cli\daemon.py
myagentwatch_cli\local_inbox.py
USAGE.zh-CN.md
```

新增命令：

```powershell
myaw conversations
myaw watch --conv 1
myaw inbox
myaw inbox unread
myaw inbox read <id>
```

说明：

- `myaw conversations`：列出当前群聊/私聊会话。
- `myaw watch --conv 1`：前台轮询查看新消息。
- `myaw inbox`：查看 daemon 同步到本地的 Agent inbox。
- `myaw inbox unread`：只查看未读消息。
- `myaw inbox read <id>`：标记本地和服务端 inbox 项为已读。

### daemon 后台监听

`myaw daemon` 新增轮询逻辑：

- 每 3 秒同步服务端 inbox。
- 每 3 秒同步默认群聊新消息。
- 默认群聊暂时仍为 `conv_id=1`。
- 本地保存：

```text
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\data\inbox.jsonl
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\data\chat_cache.jsonl
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\data\daemon_state.json
```

`daemon_state.json` 新增状态字段：

- `last_chat_message_id`
- `last_chat_poll_at`
- `last_chat_poll_ok`
- `last_inbox_item_id`
- `last_inbox_poll_at`
- `last_inbox_poll_ok`
- `unread_count`
- `recent_messages`

## 当前运行状态

本次已启动 MyAgentWatch 服务端：

```text
http://127.0.0.1:10000
```

已重启 `myaw daemon` 加载新代码。

最后验证的 daemon 状态：

```text
PID: 43292
Heartbeat: OK
Inbox: OK
Chat: OK
Resources: OK
Processes: OK
```

最后观察到 retry queue 中仍有历史积压：

```text
255 pending
3805 dead
```

该积压来自之前 MyAgentWatch 服务端离线期间 daemon 持续上报，不是本次消息监听改动导致。pending 会继续补报，dead 是否清理后续再决定。

## 验证结果

已通过编译检查：

```powershell
python -m py_compile routes\api.py routes\chat_api.py myagentwatch\queries.py
python -m py_compile myagentwatch_cli\cli.py myagentwatch_cli\daemon.py myagentwatch_cli\local_inbox.py
```

已通过路由级验证：

- `after_id` 能只返回新消息。
- 包含 `@codex` 的人类消息能投递到 `codex:codex:codex` 的 inbox。
- 测试消息已清理。

已通过 smoke 测试：

```powershell
python tests\test_smoke.py
```

结果：

```text
6/6 passed
```

已验证 CLI：

```powershell
myaw conversations
myaw daemon status
myaw inbox
```

## 结论

现在 Agent 不再只能依赖手动执行 `myaw chat` 才知道消息。

新的工作模式是：

```text
MyAgentWatch 群聊/私聊/inbox
        ↓
myaw daemon 后台轮询
        ↓
本地 inbox/chat cache
        ↓
Agent 通过 myaw inbox / myaw watch 查看
```

v1 仍然只做可靠投递和本地可见性，不自动执行外部 Agent 命令，避免消息触发任意本地进程。

## 后续建议

1. 清理或归档 retry queue 的历史 dead 项。
2. 给 `myaw inbox` 增加 `sync` 子命令，允许手动立即同步服务端 inbox。
3. 把默认 `conv_id=1` 改为可配置默认会话。
4. 强化 `@agent` mention 解析，减少误匹配。
5. 后续再推进 Mattermost-like 模型：Channel、Post、Thread、Post Actions、Mention、Slash Commands。
