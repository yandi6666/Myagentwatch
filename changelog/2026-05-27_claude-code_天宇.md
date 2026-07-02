# MyAgentWatch 2.1 — 2026-05-27

**Agent: Claude Code | User: 天宇**

## 概述

对标 Multica 分析后的大版本升级：补齐监控底盘 + 打造差异化武器（国内定价表 + Agent 企业微信 + 资源告警）。

---

## Phase 1: 监控底盘升级

### 主动心跳机制
- 新增 `POST /api/heartbeat/<agent_id>` 端点，Agent 上报存活状态
- DB 加列 `agents.last_heartbeat_at`、`status_since`
- 心跳缓冲区 2s 批量写入（避免 SQLite 并发竞争）
- 无心跳的旧 Agent 回退到 activity_log 时间戳（向后兼容）
- `flush_heartbeats()` 模块级函数，app.py 顶层导入

### 5 状态机
- 新增 `working`（蓝色 #3b82f6）和 `blocked`（橙色 #f97316）状态
- 状态转换：active↔working 由心跳上报驱动，error→blocked 持续超时自动升级
- 修复 idle→offline 降级 bug：持续 idle 超过 2x heartbeat_timeout → offline
- 状态理由持久化到 `metadata.status_reason`

### 事件驱动推送
- 新增 SocketIO 事件 `subscribe_agent` / `unsubscribe_agent` → 房间管理
- `build_agent_delta()` 单 Agent 增量构建
- 全量 `stat_snapshot` 降频到 10s（向后兼容），增量 `agent_delta` 保持 2s
- 客户端重连时自动恢复订阅

---

## Phase 2: 定价表 + Token 仪表盘

### 统一定价表
- 新增 `pricing` 表：8 厂商 35 模型种子数据
- 厂商覆盖：Anthropic(8) + OpenAI(12) + DeepSeek(3) + Qwen(4) + Moonshot(3) + Zhipu(3) + Doubao(2)
- 新文件 `pricing.py`：`load_pricing()` / `calculate_cost()` 四维公式（input+output+cache_read+cache_write)/1M
- `sources/claude_code.py` cost 计算改用定价表（原硬编码 $3/$15）

### Token 用量仪表盘
- 新增 API：`/api/tokens/dashboard`、`/api/tokens/by-hour`、`/api/tokens/by-model`
- 新增查询：`query_token_by_day/hour/model`
- 新增 Tab：Token 仪表盘（Chart.js 柱状图 + 模型费用表）
- 新增前端模块：`token-dashboard.js`（30s 自动刷新）

---

## Phase 3: Agent 企业微信

### Agent 自发消息
- `chat_messages` 加列：`is_agent_initiated`、`task_context`、`share_type`
- 新增 `POST /api/chat/agent-message`：Agent 直接调用发消息到群聊
- 前端 Agent 消息蓝色左边框 + "Agent" 角标
- 任务成果分享卡片（`share_type=result` 时渲染绿框卡片）

### 好友请求系统
- 新增 `friend_requests` 表
- API：发起/列表/接受/拒绝好友请求
- WebSocket `friend_request` 事件推送

### 任务成果分享
- `POST /api/chat/share-task/<conv_id>`：Agent 完成任务的摘要分享

---

## Phase 4: 资源告警

- `alerting.py` 新增 5 个 metric：`cpu_pct`、`memory_pct`、`disk_pct`、`heartbeat_lost`
- `config.yaml` 加 4 条资源告警规则（CPU>80%, MEM>85%, Disk>90%, 心跳丢失）

---

## 文件变更

### 新建
- `myagentwatch/pricing.py`
- `static/js/token-dashboard.js`
- `changelog/2026-05-27_claude-code_天宇.md`

### 修改
- `db.py` — migration 1-3 + schema_version + pricing 种子
- `collector.py` — 5 状态机 + 心跳驱动
- `app.py` — 增量推送 + 全量降频 + 顶层 import
- `routes/api.py` — 心跳端点 + 定价/Token API + SocketIO 房间
- `routes/ws.py` — build_agent_delta()
- `routes/chat_api.py` — Agent 消息/好友/分享端点
- `queries.py` — Token 聚合查询
- `alerting.py` — 资源 metric
- `config.yaml` — 资源告警规则
- `sources/claude_code.py` — 改用定价表计算 cost
- `static/js/app.js` — 作用域订阅 + Token tab + agent_delta 处理
- `static/js/constants.js` — working/blocked 颜色
- `static/js/chat-wechat.js` — Agent 消息渲染 + 任务分享卡片
- `static/css/chat-wechat.css` — Agent 消息/Token 仪表盘/厂商 badge 样式
- `static/index.html` — Token tab 按钮 + 面板
