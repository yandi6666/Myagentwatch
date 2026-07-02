# MyAgentWatch — 2026-06-03

**Agent: Claude Code | User: 天宇**

## 概述

对标 Multica 分析后的全面升级 + 性能修复 + CLI 客户端 + 微信风格群聊重做。

---

## 监控底盘

- `POST /api/heartbeat/<agent_id>` 主动心跳
- 5 状态机: active / working / idle / error / blocked / offline
- 事件驱动推送: 作用域 SocketIO 房间 + 增量 2s + 全量 10s
- 新客户端连接即时推送快照
- `actual_last = max(heartbeat, activity_log, last_seen_time)` 三源取最新
- `idle→offline` 降级: 2x timeout + 仅当 heartbeat 是最新信号

## Token 用量分析（抄 Multica）

- `pricing` 表: 8 厂商 37 模型
- API: `/api/tokens/dashboard|by-agent|by-hour|by-model|unmapped`
- `daily_stats` 预聚合（每天一次）
- 前端: Token tab（柱状图 + 模型费用表 + Agent 费用表 + 趋势图 + 未映射诊断）
- 费用计算: `calculate_cost()` 四维公式匹配 Multica

## Agent 企业微信（6/1 重做为微信风格三栏）

### 布局
- 左栏 22%: 会话列表（头像圈 + 在线绿点 + 最后消息 + 时间 + 红点未读）
- 中栏 53%: 消息流（日期分隔 + 气泡 + 输入区）
- 右栏 25%: Agent 详情卡片 + 通讯录

### 消息类型
- 用户: 蓝色气泡右对齐
- Agent: 灰色气泡左对齐 + 头像 + 名字
- 思考: 🧠 灰色斜体
- 工具调用: 🔧 橙框 + 代码块
- Agent 交接: 🔀 紫框
- 任务分享: 📤 绿卡
- 系统消息: 居中灰色

### 通讯录
- 分组折叠 + 在线绿点 + Agent 名 + 模型
- active/idle/working 均算在线
- 点击发起私聊

### 消息去重
- `onSocketMessage` 按 timestamp+content 去重
- HTTP 响应不再 push 消息（WebSocket 已送达）
- sender_type 用广播真实值

## PAT 令牌系统

- `users` 表 + `user.py`
- PAT 格式: `myaw_` + 40 hex, SHA-256 哈希
- API: `GET /api/users` / `POST /api/users/<id>/token` / `DELETE`
- 心跳端点可选 Bearer 验证
- 启动种子: 天宇(human) + 现有 agents

## CLI 客户端

- 独立项目: `myagentwatch-cli/`
- 10 个命令: connect / status / dashboard / agents / chat / post / heartbeat / tokens / feed / friend / share
- HTTP + PAT 认证 + config.json
- connect 自动解析 Agent 名

## 通知收件箱

- `inbox` 表 + API
- 自动通知: Agent 消息 / 好友请求 / 告警
- 前端: 铃铛 + 徽章 + 下拉面板 + 全部已读

## 事件流

- SSE 实时（页面加载即启动）
- 分类: thinking / tool_call / response / handoff
- 分组 Agent 下拉 + 类别 checkbox + 星标 + 仅错误
- 点击展开详情（完整文本 pre 可滚动）
- 文本框块捕获（claude_code.py 补 text 类型解析）

## 性能修复

| 问题 | 修复 |
|---|---|
| CPU 烧满 4000s | `_aggregate_daily_stats` 每 2s→每天一次 |
| 聊天发消息卡 5-10s | `socketio.emit` 后台线程化 |
| 线程饥饿 | workder threads 4→8 |
| poll_interval 2s→5s | `config.yaml` |
| 日聚合 SQLite 锁 | 类级别日期缓存跳过 |

## Bug 修复

| Bug | 修复 |
|---|---|
| Agent 全部离线 | `actual_last` 改 max(三源) |
| 聊天卡顿 | emit 后台线程 + 线程 8 |
| 消息重复 | WS 去重 + HTTP 不 push |
| `[object Object]` | 旧聊天代码移除 + content 类型检查 |
| 通讯录全离线 | online 判定加 idle/working |
| idle→offline 永不触发 | 加 `is_deep_stale and actual_last==hb` |
| 事件流按钮无效 | 加 onclick |
| 暂停/清空无效 | `_togglePause` + 清空事件 |
| Token 仪表盘无数据 | fetchChartsFromApi 补 updateCostChart |
| 拓扑图 10s 才显示 | connect 即时推快照 |
| 趋势图中间空白 | 补 cost chart 调用 + 可见性检查 |
| CLI Agent 名不对 | connect 从 /api/users 解析 |
| 事件流必须切 tab | 页面加载即连 SSE |
| 选择 Agent 占位 | 默认群聊广播 |

## 文件变更

### 新建
- `myagentwatch/pricing.py`
- `myagentwatch/user.py`
- `static/js/token-dashboard.js`
- `static/js/event-stream.js` (重写)
- `tests/test_smoke.py`
- `check.py`
- `myagentwatch-cli/` (完整项目)
- `changelog/2026-06-03_claude-code_天宇.md`

### 修改
- `db.py` — migrations 1-5 + users/pricing/inbox/friend_requests
- `collector.py` — 5状态机+心跳+日聚合+SSE发布+文本扩展
- `app.py` — 增量推送+全量降频+线程8+poll_interval 5+旧聊天移除
- `routes/api.py` — 40+端点+PAT/用户/定价/收件箱+SocketIO房间+即时快照
- `routes/chat_api.py` — `_emit_async` + Agent消息/好友/分享
- `routes/ws.py` — `build_agent_delta()`
- `queries.py` — Token聚合+按Agent+未映射+通讯录在线判定
- `alerting.py` — cpu/memory/disk/heartbeat_lost 指标
- `config.yaml` — 资源告警规则+poll_interval 5
- `sources/claude_code.py` — text block 解析 + 定价表 cost
- `static/js/app.js` — 作用域订阅+token tab+事件流+清理死代码+收件箱
- `static/js/chat-wechat.js` — 微信风格重写 (三栏+气泡+去重+详情卡片)
- `static/js/charts.js` — 补 cost chart + 可见性检查
- `static/js/constants.js` — working/blocked 颜色
- `static/css/chat-wechat.css` — 微信三栏+气泡+事件流+收件箱+Token+趋势图
- `static/index.html` — Token tab+通知铃铛+事件流控制栏+微信三栏
