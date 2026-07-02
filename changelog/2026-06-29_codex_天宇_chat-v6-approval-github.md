# 2026-06-29 MyAgentWatch Chat v6 收口记录

执行人：Codex  
维护者：天宇

## Summary

完成 MyAgentWatch Chat v6：群聊 task card 操作、服务端 task approval 闭环、CLI/daemon 审批可见性、AGPL-3.0-only 发布材料和 smoke 测试覆盖。

## 服务端

- schema 升级到 v12。
- `agent_tasks` 新增 approval 字段：
  - `approval_status`
  - `approval_required`
  - `approved_by`
  - `approved_at`
  - `rejected_by`
  - `rejected_at`
  - `rejected_reason`
- `reply` 默认 `not_required`。
- `review`、`code_change`、`shell_command`、`custom` 默认 `pending`。
- daemon claim 只领取 `not_required` 或 `approved` 的 task。
- 新增 task API：
  - `POST /api/agent/tasks/<id>/approve`
  - `POST /api/agent/tasks/<id>/reject`
  - `POST /api/agent/tasks/<id>/retry`
  - `GET /api/agent/tasks/<id>/context`
- approve/reject/retry/cancel/claim/start/complete/fail 均继续写入 `agent_task_events`。

## 网页群聊

- 群聊消息里的 task card 显示：
  - task 状态
  - approval 状态
  - runner attempts / lease
  - 最近事件
  - last error
- task card 新增操作：
  - 查看
  - 批准
  - 拒绝
  - 重试
  - 取消
- 右侧栏新增 Task Context 视图：
  - 来源会话和原消息
  - 线程摘要
  - inbox 记录
  - approval 状态
  - runner lease/attempt
  - events 时间线
- 附件摘要渲染补齐。
- Socket.IO task 更新后继续刷新群聊和会话列表。

## CLI / daemon

- `myaw tasks` 新增：
  - `approve <id>`
  - `reject <id> --reason "..."`
  - `retry <id>`
  - `events <id>`
- `myaw tasks show <id>` 显示 approval 字段。
- `myaw runner test --task <id>` 显示：
  - approval 是否允许
  - 本机 claim policy 是否允许
  - agent 是否匹配
  - command policy / shell allowlist 是否允许
  - 最终是否可 claim

## GitHub 发布准备

- MyAgentWatch 和 myagentwatch-cli 均新增：
  - `LICENSE`
  - `README.md`
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `RELEASE_CHECKLIST.md`
- 两个 `pyproject.toml` 声明：
  - `license = "AGPL-3.0-only"`
  - `authors = [{ name = "Tianyu" }]`
  - AGPL OSI classifier
- `.gitignore` 补充排除：
  - 数据库
  - 日志
  - token/key/pem/secret
  - local config
  - daemon data
  - cache/build 输出

## 验证

- `python -m py_compile app.py myagentwatch\db.py myagentwatch\agent_tasks.py myagentwatch\queries.py routes\agent_tasks_api.py routes\chat_api.py`
- `python -m py_compile myagentwatch_cli\cli.py myagentwatch_cli\daemon.py myagentwatch_cli\client.py`
- `node --check static\js\chat-wechat.js`
- `node --check static\js\app.js`
- `python tests\test_smoke.py`
  - 13/13 passed
- `python -m myagentwatch_cli.cli tasks --help`
- `python -m myagentwatch_cli.cli runner test --help`

## 注意

- 发布扫描发现旧 changelog / legacy heartbeat archive 中有本机路径记录；本次没有改历史文件。
- 发布 GitHub 前建议人工决定是否保留这些历史记录。
- `LICENSE` 当前使用 SPDX 明确版并链接 GNU 官方 AGPL 全文；如需要 GitHub 更强识别，可后续替换为完整 AGPL-3.0-only 全文。

