# 2026-06-29 Chat v5 Runner Loop

作者：Codex  
用户：天宇  
范围：MyAgentWatch / myagentwatch-cli

## 背景

Chat v2 已完成消息、线程、附件底座；v3 已引入 `agent_tasks` 和权限模型；v4 已补频道成员、提及、context 和 task card。v5 本次重点是把 `agent_tasks` 做成可安全执行、可观测、可恢复的 runner loop。

## 服务端

- 数据库 schema 升级到 v11。
- `agent_tasks` 新增：
  - `lease_expires_at`
  - `attempt_count`
  - `max_attempts`
  - `last_error`
- 新增 `agent_task_events`：
  - 记录 `created / claimed / requeued / started / completed / failed / cancelled` 等事件。
  - 每条事件包含 actor、message、data_json、created_at。
- claim task 时写入 lease，并递增 attempt。
- daemon claim 前会恢复过期 lease：
  - 未超过 `max_attempts`：回到 `queued`，记录 `requeued`。
  - 超过 `max_attempts`：标记 `failed`，记录失败事件。
- start / complete / fail / cancel 都会写事件。
- start / fail 会回写原会话线程里的 `task_status` 消息。
- `GET /api/agent/tasks/<id>` 返回 task 时带 `events`。
- 新增 `GET /api/agent/tasks/<id>/events`。
- 新增 `POST /api/daemon/tasks/recover-expired`。
- `POST /api/daemon/tasks/claim` 支持 `lease_seconds`。
- `POST /api/daemon/tasks/<id>/start` 支持 `actor_id`。

## CLI / daemon

- `data/daemon_policy.json` 升级为 policy v2。
- 新增 policy 字段：
  - `policy_version`
  - `lease_seconds`
  - `task_timeout_seconds`
  - `shell_allowlist`
- daemon claim 时把 `lease_seconds` 传给服务端。
- `shell_command` 必须通过本机 `shell_allowlist`，否则不会执行，task 会失败并写事件。
- 新增 CLI：
  - `myaw runner status`
  - `myaw runner status --json`
  - `myaw runner test --task <id>`
- `runner test` 只做 dry-run，不执行命令。
- `myaw tasks show <id>` 会显示 attempt、lease、last_error 和最近 events。

## 前端

- task card 显示 runner 摘要：
  - attempt
  - lease
  - last error
  - 最近 events
- 前端同时监听旧 `task_update` 和新 `agent_task_update`。
- 当前在群聊页时，task 更新会自动刷新会话列表和消息区。

## 验证

- 服务端 Python 编译通过。
- CLI Python 编译通过。
- `static/js/chat-wechat.js` 语法检查通过。
- `static/js/app.js` 语法检查通过。
- `python tests/test_smoke.py` 通过：12/12。
- `python -m myagentwatch_cli.cli runner --help` 通过。
- `python -m myagentwatch_cli.cli runner status` 通过，当前默认安全策略为 `autostart=false`。

## 关键约束

- v5 没有开放默认自动执行。
- 默认只允许安全配置下的 `reply`。
- 写代码和 shell 仍必须显式配置服务端权限、本机 policy 和命令模板。
- shell 额外要求本机 allowlist。
