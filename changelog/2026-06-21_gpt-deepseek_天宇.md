# MyAgentWatch 修改日记 — 2026-06-21

**修改者：GPT、DeepSeek**  
**用户：天宇**  
**主题：P0-C myagentwatch-cli daemon 健壮性与验收闭环**

## 背景

本次工作延续 P0-A / P0-B 的监控下沉方向：

`myagentwatch-cli 本机采集 -> POST 到 MyAgentWatch -> MyAgentWatch 入库 -> daemon 后台持续上报 -> 失败队列可恢复`

P0-C 的重点不是新增功能页面，而是让 daemon 更可靠、更可观察、更容易验收。

DeepSeek 先完成前置盘点和验收清单，GPT 负责核心代码实现、异常场景修复和最终验证。

## DeepSeek 完成内容

DeepSeek 交付文件：

```text
C:\Users\天宇\Desktop\claude-win32-x64\P0-C-DeepSeek前置交付.md
```

主要贡献：

- 梳理 P0-B daemon 当前状态。
- 整理 daemon start / stop / restart / status / logs 的验收清单。
- 提出 retry queue 断连与恢复验证方案。
- 指出 daemon 日志过少、queue 缺少直接查看命令、stale PID 需要验证等问题。
- 明确 P0-C 仍不做网页、不启用 `10001`、不迁移中央数据库。

## GPT 完成内容

### retry queue 增强

修改文件：

```text
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\myagentwatch_cli\queue.py
```

新增能力：

- retry queue 增加 `last_error`。
- retry queue 增加 `last_failed_at`。
- 新增 `details()`，用于查看 pending / dead 队列详情。
- `consume()` 增加事件回调，方便 daemon 记录补报成功和 dead 状态。

### daemon 可观测性增强

修改文件：

```text
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\myagentwatch_cli\daemon.py
```

新增日志：

- 重复启动被忽略。
- stale PID 被清理。
- stop marker 写入。
- force stop。
- 失败上报进入 retry queue。
- retry queue 自动补报成功。
- retry queue 进入 dead。
- 每 60 秒输出一次 summary。

`daemon status --json` 新增字段：

- `pid_file_pid`
- `stale_pid`
- `pid_file`
- `state_file`
- `log_file`
- `queue_file`

### CLI 命令增强

修改文件：

```text
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\myagentwatch_cli\cli.py
```

新增命令：

```powershell
myaw daemon queue
myaw daemon queue --json
myaw daemon cleanup-dead
```

用途：

- 查看 retry queue 当前状态。
- 查看失败原因摘要。
- 查看最早 pending、最新 pending、下一次 retry 时间。
- 清理 dead 队列。

### Windows 配置兼容修复

修改文件：

```text
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\myagentwatch_cli\client.py
```

修复：

- `load_config()` 改为 `utf-8-sig`。
- `save_config()` 显式使用 UTF-8。

原因：

- P0-C 验证过程中发现 Windows PowerShell 5 的 `Set-Content -Encoding UTF8` 会写入 BOM。
- 旧版 Python `json.load()` 读取带 BOM 的 `config.json` 会报错，导致 daemon 无法启动。

### 验证脚本

新增文件：

```text
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\scripts\verify_p0c.ps1
```

验证内容：

- daemon start / status / restart / logs。
- 重复 start 不产生第二个 daemon。
- stale PID 可以被 start / stop 清理。
- 临时把 server 改成 `http://127.0.0.1:19999` 模拟断连。
- 断连后失败上报进入 retry queue。
- 恢复原配置后 retry queue 自动补报并清空。
- MyAgentWatch 数据库中的 `agent_resources` / `agent_processes` 继续增长。
- 验证结束后恢复原配置，确保 daemon 保持运行。
- 临时 config 备份会自动删除，避免额外留下 PAT 副本。

### 使用手册同步

修改文件：

```text
C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\USAGE.zh-CN.md
```

更新内容：

- 第 17 节改为正式后台 daemon 说明。
- 补充 `daemon queue`、`daemon cleanup-dead`、`daemon logs`。
- 补充 P0-C 验证脚本用法。
- 标注旧的隐藏心跳脚本属于早期入口，后续建议由正式 daemon 接管。

## 验证结果

已通过：

- Python 语法检查。
- PowerShell 脚本语法检查。
- `verify_p0c.ps1` 完整验收两次。
- 断连时 heartbeat、resources、processes 共 3 条上报进入 retry queue。
- 恢复配置后 3 条全部自动补报成功。
- retry queue 最终为 `0 pending, 0 dead`。

最终 daemon 状态：

```text
PID: 86192
Agent: codex:codex:codex
Heartbeat: OK
Resources: OK
Processes: OK
Retry queue: 0 pending, 0 dead
```

## 本次没有做的事

- 没有新增网页。
- 没有启用 `10001`。
- 没有修改 MyAgentWatch 前端。
- 没有迁移中央数据库。
- 没有复制或移动项目目录。

## 结论

P0-C 完成后，`myagentwatch-cli` 的 daemon 已经从“能跑”提升到“能查、能验、能恢复”。

这为后续 P0-D / P1 做更完整的 Agent 侧监控下沉打下基础。
