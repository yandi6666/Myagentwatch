# MyAgentWatch 最终架构方案

> 量化交易AI团队通用监控工具  
> 目标：打破AI Agent黑盒，实时追踪全链路行为与成本  
> 日期：2026-05-03

---

## 一、技术栈

```
后端:
  Python 3.12          → Flask 3.x
  Flask-SocketIO       → WebSocket 实时推送
  APScheduler          → 定时任务 (5s采集 + 小时聚合)
  PyYAML               → config.yaml 解析
  psutil               → 系统资源监控

前端:
  Chart.js (CDN)       → 柱状图 / 折线图
  dagre + d3.js (CDN)  → DAG 交互流程图
  socket.io-client     → WebSocket 客户端
  CSS 纯手写            → 深色主题

存储:
  SQLite3 (只读)        → opencode.db (源数据)
  SQLite3 (读写)        → myagentwatch.db (内部聚合)

部署:
  Docker + docker-compose
```

---

## 二、数据源分析

### 主力数据源：`opencode.db` (SQLite)

| 表 | 可用监控字段 |
|---|---|
| `session` | id, parent_id, title, slug, time_created/updated, directory, summary_additions/deletions/files |
| `message` | id, session_id, data JSON: `role`, `agent` (plan/build), `mode`, `modelID`, `providerID`, `cost`, `tokens`{input/output/reasoning/cache}, `finish` |
| `part` | id, message_id, session_id, data JSON: `type` (text/reasoning/tool/step-start/step-finish), `tool` name, `callID`, `state.status`, `tokens`, `cost` |

### 辅助数据源：日志文件 (`~/.local/share/opencode/log/*.log`)

- 格式：`LEVEL TIMESTAMP +ELAPSED service=SERVICE_NAME key=value... message`
- 可提取：LLM调用耗时、服务启动/停止事件、工具注册清单、异常栈、权限评估

**策略**：SQLite覆盖80%需求，日志补充运行时事件（异常、延迟、服务状态）。

---

## 三、项目目录结构

```
~/myagentwatch/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── app.py                      # Flask + SocketIO 入口
├── config.yaml                 # 配置文件
├── myagentwatch/
│   ├── __init__.py
│   ├── db.py                   # myagentwatch.db 管理 (建表/迁移)
│   ├── config.py               # config.yaml 加载
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py             # SourceInterface 抽象
│   │   ├── opencode_db.py      # SQLite 数据源
│   │   ├── opencode_log.py     # 日志数据源
│   │   └── system.py           # 系统监控 (psutil)
│   ├── collector.py            # 采集调度器 (APScheduler 5s)
│   ├── aggregator.py           # Token/成本聚合引擎
│   ├── alerting.py             # 告警规则引擎
│   ├── parser.py               # 日志正则解析器
│   └── websocket.py            # SocketIO 事件处理
├── static/
│   ├── index.html
│   ├── css/dashboard.css
│   └── js/
│       ├── app.js              # 主入口
│       ├── dashboard.js        # 仪表盘逻辑
│       ├── flow.js             # dagre+d3 流程图
│       └── charts.js           # Chart.js 图表
└── tests/
    ├── test_collector.py
    └── test_parser.py
```

---

## 四、MyAgentWatch 内部 SQLite 设计 (`myagentwatch.db`)

```sql
-- 数据源注册（支持多 OpenCode 实例）
CREATE TABLE data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- "local-opencode", "trading-server-1"
    source_type TEXT NOT NULL,       -- "opencode_db"
    db_path TEXT NOT NULL,
    log_dir TEXT,
    enabled INTEGER DEFAULT 1,
    last_sync_time INTEGER,
    created_at INTEGER
);

-- Agent 发现与注册（自动发现 + 配置增强）
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,              -- 自动发现: "plan" / "build"
    display_name TEXT,               -- 配置映射: "DeepSeek-V4-Pro"
    source_id INTEGER REFERENCES data_sources(id),
    group_name TEXT,                 -- "最高决策层" / "代码生成层"
    agent_type TEXT,                 -- "plan"/"build"/"subagent"
    model_id TEXT,                   -- "deepseek-v4-pro"
    provider_id TEXT,                -- "deepseek"
    status TEXT DEFAULT 'inactive',  -- active/inactive/error
    last_seen_time INTEGER,
    metadata TEXT,                   -- JSON 附加属性
    created_at INTEGER,
    updated_at INTEGER
);

-- 会话
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES agents(id),
    title TEXT,
    slug TEXT,
    directory TEXT,
    status TEXT,                     -- active/idle/archived
    parent_id TEXT,                  -- 子Agent派生追踪
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

-- Token 消耗记录 (时间序列)
CREATE TABLE token_records (
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

-- 工具调用记录 (行为追踪)
CREATE TABLE tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    agent_id TEXT,
    message_id TEXT,
    part_id TEXT,
    tool_name TEXT,                  -- "bash", "read", "write", "task" ...
    call_id TEXT,
    status TEXT,                     -- pending/completed/failed
    description TEXT,
    exit_code INTEGER,
    duration_ms INTEGER,
    error_output TEXT,
    timestamp INTEGER
);

-- 行为日志 (细粒度)
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    agent_id TEXT,
    event_type TEXT,                 -- "reasoning"/"text_output"/"tool_call"/"file_edit"/"start"/"end"
    data TEXT,                       -- JSON
    severity TEXT DEFAULT 'info',
    timestamp INTEGER
);

-- 运维健康记录
CREATE TABLE health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER,
    metric TEXT,                     -- "cpu"/"memory"/"disk"/"uptime"/"active_sessions"
    value REAL,
    unit TEXT,
    timestamp INTEGER
);

-- 日聚合统计
CREATE TABLE daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    date TEXT,                       -- "YYYY-MM-DD"
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

-- 告警记录
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT,
    agent_id TEXT,
    level TEXT,                      -- info/warn/critical
    message TEXT,
    is_active INTEGER DEFAULT 1,
    created_at INTEGER,
    resolved_at INTEGER
);
```

---

## 五、配置驱动设计 (`config.yaml`)

```yaml
# MyAgentWatch 配置 (可选，无此文件时自动从数据源发现)
version: 1

# 数据源定义
data_sources:
  - name: "main-opencode"
    type: "opencode_db"
    db_path: "/data/opencode/opencode.db"
    log_dir: "/data/opencode/log"
    enabled: true
  # - name: "trading-opencode"
  #   type: "opencode_db"
  #   db_path: "/mnt/trading/.local/share/opencode/opencode.db"
  #   log_dir: "/mnt/trading/.local/share/opencode/log"
  #   enabled: false

# Agent 元数据增强 (可选)
agent_meta:
  "plan":
    display_name: "DeepSeek-V4-Pro (主控)"
    group: "最高决策层"
  "build":
    display_name: "代码生成Agent"
    group: "代码生成与系统维护层"

# 告警规则
alert_rules:
  - name: "agent_idle"
    description: "Agent超时无活动"
    metric: "last_seen_delta"
    condition: ">"
    threshold: 3600
    level: "warn"
  - name: "high_cost"
    description: "单会话成本超限"
    metric: "session_cost"
    condition: ">"
    threshold: 5.0
    level: "warn"
  - name: "tool_failure_rate"
    description: "工具调用失败率过高"
    metric: "tool_failure_pct"
    condition: ">"
    threshold: 20
    level: "critical"
  - name: "cache_miss_rate"
    description: "缓存命中率过低"
    metric: "cache_hit_pct"
    condition: "<"
    threshold: 30
    level: "info"

# 轮询配置
poll_interval: 5       # 秒
write_interval: 15     # 秒，批量写入
```

---

## 六、核心模块设计

### 6.1 数据源适配器模式 (`sources/`)

```
SourceInterface (抽象基类)
├── OpenCodeDBSource      → 读取 opencode.db
├── OpenCodeLogSource     → 解析日志文件
└── SystemSource          → psutil 采集系统资源
```

每个适配器实现三个方法：
- `discover_agents() → List[Agent]` — 自动发现Agent
- `collect(since_timestamp) → RawData` — 增量采集
- `health_check() → Dict` — 数据源自身健康

### 6.2 Agent 自动发现算法

```
discover_agents():
  for source in data_sources:
    SQL → SELECT DISTINCT
            json_extract(data, '$.agent') as name,
            json_extract(data, '$.modelID') as model,
            json_extract(data, '$.providerID') as provider
          FROM message
          WHERE json_extract(data, '$.agent') IS NOT NULL
    merge with config.agent_meta → display_name, group
    upsert into agents table
```

### 6.3 增量采集策略

- **SQLite**：记录 `last_sync_time`，查询 `WHERE time_updated > last_sync`
- **日志文件**：记录上次读取位置（文件名+行号），seek到偏移量继续读
- **系统资源**：每次全量采集（psutil开销极小）

### 6.4 数据聚合引擎

```
每小时运行:
  SELECT SUM(tokens_input), SUM(cost), ...
  FROM token_records
  WHERE timestamp BETWEEN day_start AND now
  GROUP BY agent_id
  → 写入 daily_stats
```

---

## 七、API 设计 (Flask Blueprint)

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/agents` | GET | Agent 列表及实时状态 |
| `/api/agents/<id>` | GET | 单个 Agent 详情 + 最近活动 |
| `/api/sessions` | GET | 活跃/历史会话列表 |
| `/api/sessions/<id>` | GET | 会话详情 + 完整时间线 |
| `/api/stats/overview` | GET | 仪表盘概览 (活跃数/Token/成功率/成本) |
| `/api/stats/tokens` | GET | Token 拆解 (按agent/model/小时) |
| `/api/stats/charts` | GET | 图表数据 (1h延迟折线, Token柱状) |
| `/api/timeline` | GET | 活动时间线 |
| `/api/timeline/flow` | GET | DAG 流程图数据 |
| `/api/logs` | GET | 实时日志流 (SSE) |
| `/api/health` | GET | 系统运维状态 |
| `/api/alerts` | GET | 告警列表 |
| `/api/alerts/resolve` | POST | 解除告警 |
| `/api/config` | GET | 当前配置快照 |

### WebSocket 事件 (Flask-SocketIO)

**Server → Client:**
| 事件 | 内容 |
|---|---|
| `agent_update` | Agent状态变更 {agent_id, status, tokens_1h, ...} |
| `stat_snapshot` | 仪表盘卡片更新 {active_agents, total_tokens, cost, ...} |
| `log_line` | 实时日志行 {level, timestamp, service, message} |
| `alert_event` | 新告警 {id, rule, level, message} |
| `flow_update` | 流程图增量 {type, node_id, parent_id, data} |

**Client → Server:**
| 事件 | 内容 |
|---|---|
| `subscribe_logs` | {source_id, filters: {level, service}} |
| `unsubscribe_logs` | {source_id} |

---

## 八、前端仪表盘设计

```
┌─────────────────────────────────────────────────────────┐
│  MyAgentWatch                          [配置] [刷新: 5s] │
├──────────┬──────────┬──────────┬────────────────────────┤
│ 🟢 Agent │ 📊 Token │ ✅ 成功率│ 💰 今日成本            │
│   活跃数  │  今日消耗 │   92.3%   │  ¥3.58               │
├──────────┴──────────┴──────────┴────────────────────────┤
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ Agent Token消耗  │  │ 最近1小时请求延迟 (折线图)    │  │
│  │ (柱状图)         │  │                              │  │
│  │ ████ plan: 45K  │  │   ── plan        ── build    │  │
│  │ ██ build: 18K   │  │  2s    3s    2s    4s        │  │
│  └─────────────────┘  └──────────────────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  Agent 实时状态                                           │
│  ┌─────────┬────────┬────────┬──────┬────────┬────────┐ │
│  │ Agent   │ 状态   │ 模型    │ 会话 │ Token  │ 延迟   │ │
│  │ plan    │ 🟢在线  │ V4-Pro │ 1    │ 45.2K  │ 3.2s   │ │
│  │ build   │ 🟡空闲  │ GLM-5  │ 0    │ 0      │ -      │ │
│  └─────────┴────────┴────────┴──────┴────────┴────────┘ │
├──────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────────────────┐  │
│  │ 实时日志流        │  │ 交互流程图 (DAG)              │  │
│  │ (彩色编码+过滤)    │  │                              │  │
│  │                   │  │  user→plan→bash→text         │  │
│  │ [INFO] session..  │  │       ↓                      │  │
│  │ [WARN] snapshot.. │  │     build→read→output        │  │
│  │ [INFO] llm call.. │  │                              │  │
│  └──────────────────┘  └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

- **深色主题**：背景 `#1a1a2e`，卡片 `#16213e`，强调色 `#0f3460` + `#e94560`
- **5秒自动轮询**：`setInterval(fetch + WebSocket, 5000)`
- **彩色编码日志**：INFO=灰, WARN=黄, ERROR=红, DEBUG=浅蓝
- **DAG交互**：点击节点弹出详情抽屉，显示完整数据内容

---

## 九、Docker 部署

```dockerfile
# Dockerfile
FROM python:3.12-slim
RUN pip install flask flask-socketio flask-cors apscheduler pyyaml psutil
COPY . /app
WORKDIR /app
EXPOSE 5000
CMD ["python", "app.py"]
```

```yaml
# docker-compose.yml
services:
  myagentwatch:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ~/.local/share/opencode:/data/opencode:ro
      - ./config.yaml:/app/config.yaml
      - ./data:/app/data
    restart: unless-stopped
```

---

## 十、多实例架构图

```
                    ┌─────────────────────┐
                    │   MyAgentWatch      │
                    │   Collector (5s)    │
                    └──────┬──────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
     ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
     │ Source A  │   │ Source B  │   │ Source C  │
     │ opencode  │   │ opencode  │   │ system    │
     │ (local)   │   │ (remote,  │   │ (psutil)  │
     │           │   │  via NFS) │   │           │
     └───────────┘   └───────────┘   └───────────┘
```

只需在 `config.yaml` 添加 `data_sources` 条目即可热监控更多 OpenCode 实例。

---

## 十一、通用性保障

| 原则 | 实现 |
|---|---|
| **零硬编码 Agent 名** | Agent 从 `message.data.agent` 自动提取 |
| **零假设启动** | 无 config.yaml 时自动扫描默认路径，发现所有 Agent |
| **配置驱动** | display_name、group、告警规则 全部 config.yaml 覆盖 |
| **通用适配** | 能监控任何使用 OpenCode 的Agent团队（量化版/精简版/通用版） |
| **多实例** | SourceInterface 抽象，一套代码监控多个 opencode.db |

---

## 十二、CLI 客户端 (`myagentwatch-cli`)

独立的命令行客户端，通过 PAT 令牌连接 MyAgentWatch 服务端，方便在终端中查看 Agent 状态和进行交互。

### 项目结构

```
myagentwatch-cli/
├── pyproject.toml              # Python 包配置 (entry: myaw)
├── config.json                 # 运行时配置 (server + PAT)
└── myagentwatch_cli/
    ├── __init__.py
    ├── cli.py                  # 命令行入口 (argparse + 10 命令)
    └── client.py               # HTTP 客户端 (GET/POST/DELETE + Bearer 认证)
```

### 安装与启动

```bash
pip install -e .
myaw connect --server http://localhost:10000 --key myaw_xxx
```

### 技术实现

**client.py — HTTP 通信层：**
- 纯标准库实现 (`urllib.request`)，零外部依赖
- Bearer Token 认证（Authorization header）
- URL 自动编码（Agent ID 含空格和冒号）
- config.json 持久化（server + key + agent_name + agent_id）
- connect 时自动调用 `/api/users` 匹配 token 前缀，识别 Agent 身份

**cli.py — 命令入口：**
- argparse 子命令模式，入口点 `myaw`
- ANSI 彩色终端输出（active=绿/working=蓝/idle=黄/error=红/blocked=紫/offline=灰）
- `_box()` 函数绘制 Unicode 边框卡片

### 10 个命令

| 命令 | 参数 | 用途 |
|---|---|---|
| `connect` | `--server` `--key` | 连接服务端，自动识别 Agent 身份 |
| `status` | - | 仪表盘总览（Agent 状态 + Token 用量 + 未读通知） |
| `dashboard` | - | status + feed 合并视图 |
| `agents` | - | 列出所有 Agent（状态色 + 模型 + 令牌标识） |
| `chat` | `[message]` `[--conv]` | 读群聊消息（最近 20 条）或发送消息 |
| `post` | `<content>` | 发布 Agent 动态到群聊 |
| `heartbeat` | `--agent-id` `[--status]` `[--daemon]` | 手动心跳；`--daemon` 模式每 15s 自动发送 |
| `tokens` | `[--days]` | Token 用量（按日 + 按 Agent + 未定价模型诊断） |
| `feed` | - | 查看动态流/收件箱（按类型图标 + 未读标记） |
| `friend` | `<agent_id>` `[message]` | 发送好友请求 |
| `share` | `<title>` `[summary]` | 分享任务成果到群聊 |

### 认证流程

```
myaw connect --server http://host:10000 --key myaw_xxx
  │
  ├─ 1. 保存 server + key → config.json
  ├─ 2. GET /api/users (Bearer token)
  ├─ 3. 遍历 users，匹配 token_prefix → agent_name + agent_id
  └─ 4. 更新 config.json，后续请求自动携带 token
```

### 心跳守护模式

```bash
myaw heartbeat --agent-id "claude-code:Claude Code:deepseek-v4-pro" --daemon
# 每 15s 自动发送 POST /api/heartbeat/{agent_id}
# Ctrl+C 停止
```

守护模式用于让无内置心跳的 Agent CLI 也能维持 active 状态。

---

## 十三、功能覆盖清单

| 需求 | 实现方式 |
|---|---|
| 1.1 智能体黑盒透明化 | activity_log 表 + DAG交互流程图 + 实时日志流 |
| 1.2 全维度成本管控 | token_records 表 + daily_stats 聚合 + 按session/agent/model拆解 |
| 1.3 开发调试与故障排查 | 时序图 + 彩色日志 + 完整对话转录 |
| 1.4 生产运维保障 | health_checks 表 + 定时任务状态 + 系统资源监控 |
| 2.1 实时交互流程图 | dagre+d3.js DAG节点图，点击节点看详情 |
| 2.2 全链路行为追踪 | message→part 链 + tool_calls 记录 |
| 2.3 精细化成本统计 | input/output/reasoning/cache 四级拆解 |
| 2.4 会话与日志管理 | 会话列表+详情 + 彩色编码实时日志 + filter |
| 2.5 系统运维监控 | CPU/MEM/DISK + 活跃会话 + 告警规则引擎 |

---

## 十四、实现路径与预估时间

| Phase | 内容 | 预估工时 |
|---|---|---|
| **Phase 1: 核心骨架** | app.py入口、db.py建表、config.py加载、Flask路由基础 | 1h |
| **Phase 2: 数据采集** | OpenCodeDBSource、Collector(5s调度)、增量策略、Agent发现 | 1.5h |
| **Phase 3: API 层** | 全部 REST 端点 + WebSocket 事件 + 聚合引擎 | 1.5h |
| **Phase 4: 前端仪表盘** | HTML+CSS深色主题 + 卡片/图表/表格 + 5s轮询 | 1.5h |
| **Phase 5: 实时日志+流程图** | WebSocket日志推送 + dagre/d3 DAG交互图 | 2h |
| **Phase 6: 告警+日志源** | OpenCodeLogSource、alerting.py、告警规则 | 1h |
| **Phase 7: Docker化** | Dockerfile + docker-compose.yml + 测试 | 0.5h |

| 总计 | **约 9 小时** (含测试调试) |
|---|---|

---

## 十五、需要你的确认

在开始编码前，还想确认：

1. **Python 版本**：`python3 --version` 确认是 3.8+ ？需要确认 Flask-SocketIO 兼容性
2. **端口**：5000 端口可用？或者你想用其他端口？
3. **是否现在开始 Phase 1**？我会按 phase 逐步实现

---

> 这份方案保存在 `~/Desktop/MyAgentWatch-架构方案.md`，你可以随时查看。
