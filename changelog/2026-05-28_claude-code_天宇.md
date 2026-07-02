# MyAgentWatch 2.1 — 2026-05-28

**Agent: Claude Code | User: 天宇**

> 2026-05-28 19:30 更新

## 概述

对标 Multica 后的全面升级 + Bug 修复。15 个文件修改，3 个新文件，35 个定价模型。

---

## 新功能

### 1. 监控底盘升级

**主动心跳机制**
- `POST /api/heartbeat/<agent_id>` — Agent 上报存活状态
- `agents` 表加列 `last_heartbeat_at`、`status_since`
- 心跳缓冲区内存暂存，2s 批量写入 SQLite
- `flush_heartbeats()` 模块级函数，顶层导入，无动态 import
- 旧 Agent（无心跳）回退到 activity_log 时间戳

**5 状态机**
- 新增两态：`working`（蓝色 #3b82f6）、`blocked`（橙色 #f97316）
- 状态转换：active↔working 由心跳驱动，error→blocked 持续超时自动升级
- 修复 idle→offline 永不降级的旧 bug：2x heartbeat_timeout 后降级
- `is_deep_stale → offline` 仅对有心跳的 Agent 生效（`hb > 0` 条件）
- 无心跳 Agent 用 `last_seen_time` 三级回退（心跳 → activity_log → 发现时间戳）
- 状态理由持久化到 `metadata.status_reason`

**事件驱动推送**
- SocketIO 房间：`subscribe_agent` / `unsubscribe_agent`
- `build_agent_delta()` 单 Agent 增量构建
- 全量 `stat_snapshot` 降频 10s，增量 `agent_delta` 保持 2s
- 客户端重连自动恢复订阅
- 新客户端连接立即推送一次快照（不等 10s）
- 增量推送用缓存 Agent ID 列表，不重复查 DB

### 2. 定价表 + Token 仪表盘

**统一定价表**（新文件 `pricing.py`）
- `pricing` 表：8 厂商 35 模型种子数据
- Anthropic(8) + OpenAI(12) + DeepSeek(3) + Qwen(4) + Moonshot(3) + Zhipu(3) + Doubao(2)
- `load_pricing()` / `calculate_cost()` — 与 Multica 同款四维公式
- `sources/claude_code.py` 成本计算改用定价表（旧硬编码 $3/$15）

**Token 仪表盘**（新文件 `token-dashboard.js`）
- API：`/api/tokens/dashboard`、`/api/tokens/by-hour`、`/api/tokens/by-model`
- 查询：`query_token_by_day/hour/model`
- 前端：Chart.js 柱状图 + 模型费用表 + 厂商 badge
- Chart.js 不可用时纯文本表格兜底
- 30s 自动刷新

### 3. Agent 企业微信

- `chat_messages` 加列：`is_agent_initiated`、`task_context`、`share_type`
- `POST /api/chat/agent-message` — Agent 主动发消息
- `friend_requests` 新表 + 发起/列表/接受/拒绝 API
- 前端 Agent 消息蓝色左边框 + "Agent" 角标 + 任务分享卡片（绿色）

### 4. 资源告警

- 新增 CPU/内存/磁盘/心跳丢失 4 条告警规则
- `alerting.py` 新增 psutil 实时指标查询

### 5. UI 优化

- Token tab 集成趋势图：Daily 用量柱状图 + 模型费用表 + 三张趋势图（token 柱状/成本折线/延迟折线）
- 趋势图从仪表盘底部移至 Token tab，仪表盘不再拥挤
- 三张趋势图均检查 canvas 可见性，隐藏 tab 内不渲染

### 6. 一键检查

- `check.py`：自检脚本（冒烟测试 + 模块导入 + JS 语法 + HTML 引用完整性）
- `tests/test_smoke.py`：6 个核心链路用例
- 心跳端点输入校验：status 白名单、agent_id 长度、metadata 类型

---

## Bug 修复

| Bug | 修复 |
|---|---|
| Agent 全部显示离线 | `_mark_stale_agents` 漏读 `last_seen_time`，无心跳+无 activity 的 Agent 被误判 offline |
| idle→offline 永不发生 | 旧代码注释说会降级但没实现，加了 `is_deep_stale and hb > 0` 的降级路径 |
| 拓扑图打开后 10 秒才显示 | connect 事件加即时 `emit("stat_snapshot")` |
| 趋势图中间空白 | `fetchChartsFromApi` 漏调 `updateCostChart`，加上了+兜底字段名修正 |
| `database` is not defined | 顶层补 `from myagentwatch.db import database`，增量推送改用缓存 ID 不重复查 DB |
| cost 硬编码 `$3/$15` | `sources/claude_code.py` 改用 `calculate_cost()` |
| 动态 import flush_heartbeats | 提到模块级函数，`app.py` 顶层导入 |

---

## 文件变更

### 新建
- `myagentwatch/pricing.py`
- `static/js/token-dashboard.js`
- `tests/test_smoke.py`
- `check.py`
- `changelog/2026-05-28_claude-code_天宇.md`

### 修改
- `myagentwatch/db.py` — migration 1-3 + schema_version + pricing 种子 + chat_messages 列 + friend_requests
- `myagentwatch/collector.py` — 5 状态机 + 心跳驱动 + last_seen_time 回退
- `myagentwatch/app.py` — 增量推送 + 全量降频 + 顶层 import + 缓存 ID 列表
- `myagentwatch/routes/api.py` — 心跳 + 定价/Token API + SocketIO 房间 + 连接即推快照 + 输入校验
- `myagentwatch/routes/ws.py` — build_agent_delta()
- `myagentwatch/routes/chat_api.py` — Agent 消息/好友/分享
- `myagentwatch/queries.py` — Token 聚合查询
- `myagentwatch/alerting.py` — 资源 metric（cpu/memory/disk/heartbeat_lost）
- `myagentwatch/config.yaml` — 资源告警规则
- `myagentwatch/sources/claude_code.py` — 成本改用定价表
- `static/js/app.js` — 作用域订阅 + Token tab + agent_delta + 图表只在 Token tab 更新
- `static/js/constants.js` — working/blocked 颜色
- `static/js/charts.js` — fetchChartsFromApi 补 updateCostChart + 可见性检查 + 字段修正
- `static/js/token-dashboard.js` — Chart.js 防护 + 趋势图联动 + 清理逻辑
- `static/js/chat-wechat.js` — Agent 消息渲染 + 任务分享卡片
- `static/css/chat-wechat.css` — Agent 消息/Token 仪表盘/厂商 badge/趋势卡片样式
- `static/index.html` — Token tab + 趋势图三列布局 + 移除仪表盘底部图表 + 通知铃铛

### 7. 通知收件箱（抄 Multica inbox_item）

- `inbox` 表：recipient_type / recipient_id / type / severity / title / body / link / source_agent_id
- API：`GET /api/inbox` / `POST /api/inbox/read/<id>` / `POST /api/inbox/read-all` / `POST /api/inbox/archive/<id>`
- 事件自动写入收件箱：Agent 消息、好友请求、告警
- WebSocket `inbox_update` 实时推送
- 前端：顶部栏铃铛 + 未读徽章 + 下拉面板 + 点击已读 + 全部已读
