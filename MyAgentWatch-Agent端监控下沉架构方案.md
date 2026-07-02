# MyAgentWatch Agent 端监控下沉架构方案

作者：Codex  
用户：天宇  
日期：2026-06-21

## 1. 核心结论

MyAgentWatch 和 myagentwatch-cli 的服务对象必须彻底分清：

```text
MyAgentWatch = 用户端
myagentwatch-cli = Agent 端
```

MyAgentWatch 继续作为用户打开的监控平台，负责中央数据库、用户网页、审计回放、任务、群聊、告警、权限和可视化。

myagentwatch-cli 不做网页，不做第二套前端，不使用 iframe，不替代 MyAgentWatch。它升级为 Agent 侧 Skill / daemon / 本地采集器，负责 Agent 自己的心跳、本机资源监控、进程检测、事件上报、任务状态上报和本地失败重试。

一句话边界：

```text
myagentwatch-cli 负责采集和 Agent 自我感知。
MyAgentWatch 负责中央记录、用户展示、审计和管理。
```

## 2. 新版架构图

```text
┌──────────────────────────────────────────────┐
│ MyAgentWatch 用户端                           │
│ http://127.0.0.1:10000                        │
│                                              │
│ 给人看：                                      │
│ - 仪表盘                                      │
│ - Agent 状态总览                              │
│ - Token 成本                                  │
│ - 任务板                                      │
│ - 群聊/通知                                   │
│ - 告警中心                                    │
│ - 审计回放                                    │
│ - 权限/PAT                                    │
│ - 中央数据库                                  │
└──────────────────────▲───────────────────────┘
                       │
                       │ 上报 / 查询 / 指令
                       │
┌──────────────────────┴───────────────────────┐
│ myagentwatch-cli Agent 端                      │
│ 不做网页 UI                                    │
│ 可选本地 daemon，不面向用户                    │
│                                              │
│ 给 Agent 用：                                  │
│ - 心跳 daemon                                  │
│ - 本机资源监控 CPU/内存/C盘/GPU/网络           │
│ - Agent 进程检测                               │
│ - 工具调用/事件上报                            │
│ - 任务状态上报                                 │
│ - 群聊/团队状态查询                            │
│ - 本地缓存/失败重试                            │
│ - doctor 自检                                  │
└──────────────────────────────────────────────┘
```

## 3. 服务对象划分

### 3.1 MyAgentWatch 服务用户

MyAgentWatch 面向人类用户。用户通过它理解整个 Agent 团队：

- 哪些 Agent 在线。
- 哪些 Agent 离线、阻塞、报错。
- Token 花在哪里。
- 哪些任务正在运行。
- 谁把任务交给了谁。
- Agent 之间说了什么。
- 发生过哪些告警。
- 事后如何回放整个协作过程。

因此 MyAgentWatch 必须保留中央数据库和用户视图，不能变成空壳。

### 3.2 myagentwatch-cli 服务 Agent

myagentwatch-cli 面向 Agent。Agent 通过它理解自己和团队：

- 我是谁。
- 我是否在线。
- 我所在机器资源是否足够。
- 我当前是否应该继续执行任务。
- 我的进程是否正常。
- 我应该向 MyAgentWatch 上报什么。
- 我是否有任务、消息、告警需要处理。
- 我是否需要请求其他 Agent 或用户帮助。

因此 myagentwatch-cli 应该变成 Agent Skill，而不是用户网页。

## 4. 数据归属

### 4.1 保留在 MyAgentWatch 的中央数据

这些表和能力继续以 MyAgentWatch 为事实源：

```text
agents
token_records
tool_calls
activity_log
conversation_turns
turn_content
agent_handoffs
tasks
task_records
chat_conversations
chat_messages
friend_requests
alerts
inbox
users
pricing
daily_stats
agent_relationships
```

保留原因：

- 用户需要全局审计。
- 多 Agent 回放必须集中。
- Token 成本需要统一统计。
- 任务和群聊是团队协作记录，不能散落在多个本地 CLI。
- 权限、告警和通知面向用户，必须在用户端统一管理。

### 4.2 放到 myagentwatch-cli 的本地能力

myagentwatch-cli 第一阶段只拥有本地采集和短期缓存能力：

```text
本机资源快照
本机 Agent 进程状态
心跳循环状态
本地 daemon 状态
本地失败重试队列
最近上报结果
本地日志
doctor 自检结果
```

CLI 本地可以有轻量缓存，但它不是最终事实库。最终历史记录仍然上报到 MyAgentWatch。

## 5. 为什么资源监控需要双端都有

资源监控应该 MyAgentWatch 和 myagentwatch-cli 都有，但语义不同。

MyAgentWatch 的资源监控：

```text
用户端/中央服务所在机器是否健康。
```

myagentwatch-cli 的资源监控：

```text
Agent 所在机器是否还能继续执行任务。
```

在单机开发环境里，两边读到的 CPU、内存、磁盘可能相同。但未来多机器后，区别会非常重要：

```text
用户电脑 / 控制台机器：MyAgentWatch 资源
Agent A 机器：CLI A 资源
Agent B 机器：CLI B 资源
Agent C 机器：CLI C 资源
```

因此资源监控不是从 MyAgentWatch 移走，而是在 CLI 侧新增 Agent 视角。

## 6. myagentwatch-cli 新模块建议

```text
myagentwatch_cli/
  cli.py              # 命令入口
  client.py           # 连接 MyAgentWatch
  config.py           # CLI 配置
  daemon.py           # 后台守护，不做网页
  doctor.py           # 环境自检
  heartbeat.py        # 心跳上报
  events.py           # 工具调用/状态/日志事件上报
  queue.py            # 本地失败重试队列
  monitor/
    __init__.py
    resources.py      # CPU/内存/磁盘/GPU/网络
    processes.py      # Agent 进程检测
```

daemon 的定位：

```text
daemon = Agent 侧后台进程
daemon != 用户网页
daemon != 第二个 MyAgentWatch
```

daemon 可以长期运行，负责周期性采集和上报。CLI 命令可以调用 daemon，也可以直接调用 MyAgentWatch。

## 7. MyAgentWatch 新增接收 API 建议

第一阶段新增 Agent ingest API，而不是搬迁数据库：

```text
POST /api/agent-ingest/resources
POST /api/agent-ingest/processes
POST /api/agent-ingest/events
POST /api/agent-ingest/daemon-status
```

继续保留：

```text
POST /api/heartbeat/<agent_id>
GET  /api/agents
GET  /api/tasks
GET  /api/chat/*
GET  /api/tokens/*
GET  /api/logs/*
```

### 7.1 资源上报数据草案

```json
{
  "agent_id": "codex:codex:codex",
  "host_id": "desktop-tianyu",
  "timestamp": 1782010000000,
  "cpu_pct": 31.2,
  "memory_pct": 68.4,
  "memory_used_mb": 12103.5,
  "memory_total_mb": 32768.0,
  "disk": [
    {
      "mount": "C:",
      "used_pct": 82.1,
      "used_gb": 410.5,
      "total_gb": 500.0
    }
  ],
  "gpu": [
    {
      "name": "NVIDIA GeForce RTX",
      "util_pct": 12.0,
      "memory_used_mb": 2048,
      "memory_total_mb": 8192,
      "temperature_c": 55
    }
  ],
  "network": {
    "bytes_sent": 123456,
    "bytes_recv": 654321
  }
}
```

### 7.2 进程上报数据草案

```json
{
  "agent_id": "codex:codex:codex",
  "host_id": "desktop-tianyu",
  "timestamp": 1782010000000,
  "processes": [
    {
      "name": "codex",
      "pid": 12345,
      "running": true,
      "cpu_pct": 8.5,
      "memory_mb": 512.0,
      "command": "codex ..."
    }
  ]
}
```

### 7.3 事件上报数据草案

```json
{
  "agent_id": "codex:codex:codex",
  "timestamp": 1782010000000,
  "event_type": "tool_call",
  "severity": "info",
  "message": "Agent called shell command",
  "metadata": {
    "tool_name": "shell",
    "status": "completed",
    "duration_ms": 1200
  }
}
```

## 8. 第一阶段 P0

第一阶段目标：不大拆分，不搬中央数据库，不做网页，只让 myagentwatch-cli 具备 Agent 侧基础监控能力。

### 8.1 myaw doctor

目标：

- 检查 CLI 配置是否存在。
- 检查 MyAgentWatch 是否可连接。
- 检查 PAT 是否有效。
- 检查 Python 版本。
- 检查 psutil 等依赖。
- 检查本地 daemon 是否运行。
- 检查开机自启是否配置。

示例：

```powershell
myaw doctor
```

### 8.2 myaw monitor resources

目标：

- 一次性输出本机资源快照。
- 支持 CPU、内存、磁盘。
- 后续补 GPU、网络。

示例：

```powershell
myaw monitor resources
```

### 8.3 myaw monitor process

目标：

- 检查本机 Agent 相关进程是否存在。
- 输出进程 PID、CPU、内存、命令行。
- 让 Agent 可以知道自己或队友是否真的在跑。

示例：

```powershell
myaw monitor process
myaw monitor process --name claude
myaw monitor process --name codex
```

### 8.4 myaw daemon start/stop/status

目标：

- 启动 Agent 侧后台守护。
- 周期性心跳。
- 周期性资源采集。
- 周期性进程检测。
- 失败时写入本地队列，恢复后补发。

示例：

```powershell
myaw daemon start
myaw daemon status
myaw daemon stop
```

### 8.5 自动心跳

目标：

- daemon 启动后自动发送心跳。
- 支持状态：active、working、idle、blocked、error、offline。
- 不再依赖用户手动反复运行 `heartbeat --daemon`。

### 8.6 本地失败重试队列

目标：

- MyAgentWatch 暂时不可用时，不丢关键上报。
- 资源、事件、进程状态可以暂存。
- 恢复连接后自动补发。

第一阶段可以用 JSONL 文件实现，不急着引入本地 SQLite。

## 9. 第一阶段明确不做

第一阶段不做这些事：

- 不把 myagentwatch-cli 做成网页。
- 不新增 iframe。
- 不拆第二套前端。
- 不把 MyAgentWatch 前端搬到 CLI。
- 不把 `tasks` 表搬到 CLI。
- 不把 `chat_messages` 表搬到 CLI。
- 不把 `conversation_turns` / `turn_content` 搬到 CLI。
- 不把 `token_records` 中央历史库搬到 CLI。
- 不把 MyAgentWatch 精简成空壳。
- 不做大规模数据库拆分。
- 不复制项目目录。
- 不改现有端口策略导致冲突。

## 10. 第二阶段方向

第一阶段稳定后，再考虑：

- CLI 自动上报工具调用事件。
- CLI 自动上报 Agent 任务状态。
- CLI 提供 Agent 侧团队状态查询。
- CLI 提供 Agent 侧告警查询。
- CLI 读取 MyAgentWatch 群聊和任务，作为 Agent Skill。
- GPU 监控。
- 网络 I/O 监控。
- 多机器 host_id 管理。
- Agent 资源历史曲线。

## 11. 对 deepseek 方案的修正

deepseek 的盘点报告中，能力位置、API、数据库表整理很有价值，可以继续作为基础资料。

但其原始方案倾向于：

```text
把 myagentwatch-cli 升级成第二个完整服务端，甚至带 Web UI。
```

这个方向第一阶段不采用。

修正为：

```text
myagentwatch-cli 只做 Agent 侧 daemon / Skill / 本地采集器。
MyAgentWatch 继续做用户端和中央事实库。
```

这样既能让 Agent 侧监控能力下沉，又不会破坏 MyAgentWatch 的核心价值：全局可视化、中央审计、事后回放和用户管理。

## 12. 产品哲学

这套架构服务于两个价值主张：

```text
让你像管理微服务一样管理你的 AI Agent 团队。
让 Agent 不再是你的员工，而是你的同事。
```

MyAgentWatch 让用户看见 Agent 团队。

myagentwatch-cli 让 Agent 看见自己和队友。

用户可以管理 Agent，但 Agent 也应该拥有自我状态感知、协作感知和求助能力。这才是 Agent 团队从“被动工具”走向“协作同事”的基础。

