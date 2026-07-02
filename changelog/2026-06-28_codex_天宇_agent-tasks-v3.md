# 2026-06-28 Codex / 天宇 - Agent Tasks v3

## Summary

实现 MyAgentWatch v3 的第一阶段：Hybrid Wakeup + Agent Task Queue + 权限模型。

## Changes

- 服务端 schema 升级到 v9：
  - `users.role`
  - `users.permissions_json`
  - `users.permission_limits_json`
  - `agents.role`
  - `agents.permissions_json`
  - 新增 `agent_tasks`
- 默认权限：
  - `天宇` / `tianyu` 初始化为 `user-owner`
  - `codex:codex:codex` 初始化为 `agent-root/codex`
- 新增 Agent task helper：
  - 权限位拆分为聊天、文字回复、任务、代码、shell、autostart、权限管理。
  - `reply/review/code_change/shell_command/custom` 按能力位校验。
  - `complete_agent_task` 可把 Agent 结果回写原 chat 线程。
- 新增 API：
  - `GET /api/agent/tasks`
  - `GET /api/agent/tasks/<id>`
  - `POST /api/agent/tasks`
  - `POST /api/agent/tasks/<id>/cancel`
  - `POST /api/daemon/tasks/claim`
  - `POST /api/daemon/tasks/<id>/start`
  - `POST /api/daemon/tasks/<id>/complete`
  - `POST /api/daemon/tasks/<id>/fail`
  - `GET /api/permissions/roles`
  - `PATCH/POST /api/permissions/users/<id>`
  - `PATCH/POST /api/permissions/agents/<id>`
- Chat 触发规则：
  - 普通群聊不创建 task。
  - 私聊 Agent 和 `@agent` 创建 `reply` task。
  - `/assign`、`/run`、`/code`、`/shell` 进入对应执行型 task，但受权限限制。
- CLI：
  - 新增 `myaw tasks list`
  - 新增 `myaw tasks next`
  - 新增 `myaw tasks show <id>`
  - 新增 `myaw tasks cancel <id>`
- daemon：
  - 新增 `data/daemon_policy.json`。
  - daemon 主循环支持 task claim。
  - 默认 `autostart_enabled=false`，没有命令模板时不 claim，不启动外部命令。
  - 状态输出增加 Agent tasks 最近 claim 状态和 policy 路径。

## Validation

- `python tests\test_smoke.py`：10/10 passed。
- 服务端 `py_compile` 通过。
- CLI/daemon `py_compile` 通过。
- `python -m myagentwatch_cli.cli tasks --help` 通过。

## Notes

- 当前运行中的 MyAgentWatch 服务和 `myaw daemon` 需要重启后才会加载 v3 代码。
- v3 默认安全：服务端可以创建 task，但 daemon 不会自动启动本地 Agent CLI，除非显式配置 daemon policy。
