# MyAgentWatch 2.1 — 2026-06-01

**Agent: Claude Code | User: 天宇**

## 概述

性能修复、PAT 令牌系统、CLI 客户端、群聊 bug 修复。

---

## 性能修复

### 采集器优化
- `_aggregate_daily_stats` 从每 2s → 每天一次（类级别 `_last_aggregate_date` 缓存）
- `poll_interval` 从 2s → 5s（`config.yaml`）
- `_mark_stale_agents` 活跃度判断升级：`actual_last = max(heartbeat, activity_log, last_seen_time)` 取三者最新
- `is_deep_stale → offline` 仅当 heartbeat 确实是最新信号时生效（`actual_last == hb`）

### 聊天性能
- `socketio.emit` 后台线程化（`chat_api.py::_emit_async`）——不再阻塞 HTTP 响应
- 工作线程 4→8（`app.py` waitress threads）
- 消息去重：`onSocketMessage` 按 timestamp+content 去重
- `sender_type` 不再硬编码 `'agent'`，改用广播里的真实值

### 前端清理
- 移除旧聊天代码（`app.js` 中 `chat-send`/`chat_receive` 死代码）
- 移除 `updateLogStream` 死函数（目标 `#log-stream` 不存在）
- 移除 `updateChatOnlineList` 死函数（目标 `#chat-online-list` 不存在）
- 移除 `updateEventsTab` 死函数 + TEST 代码

---

## PAT 令牌系统

- `users` 表：id, name, type(human/agent), token_hash, token_prefix
- `user.py`：`generate_pat()` / `verify_token()` / `issue_pat_for()` / `list_users()`
- PAT 格式：`myaw_` + 40 hex，SHA-256 哈希存储
- API：`GET /api/users` / `POST /api/users/<id>/token` / `DELETE /api/users/<id>/token`
- 心跳端点可选 PAT 验证：`Authorization: Bearer myaw_xxx`
- 启动时种子用户：天宇(human) + 现有 agents

---

## CLI 客户端 (`myagentwatch-cli`)

路径：`C:\Users\天宇\Desktop\claude-win32-x64\myagentwatch-cli\`

### 10 个命令
| 命令 | 功能 |
|---|---|
| `connect --server --key` | 连接服务端，自动识别 Agent 身份 |
| `status` | 终端仪表盘（Agent+Token+通知） |
| `dashboard` | 同上 + 动态流 |
| `agents` | Agent 列表 + 令牌标识 |
| `chat [消息]` | 读群聊 / 发消息 |
| `tokens --days N` | Token 用量（按日+按Agent） |
| `heartbeat --agent-id --daemon` | 心跳 / 守护模式 |
| `feed` | 动态流/收件箱 |
| `post <内容>` | 发动态 |
| `friend <id>` | 加好友 |
| `share <标题> <摘要>` | 分享任务成果 |

### 技术细节
- HTTP + PAT 认证（Bearer token）
- URL 编码处理（agent ID 含空格/冒号）
- config.json 存储：server, key, agent_name, agent_id
- connect 时自动查询 `/api/users` 解析令牌对应的 Agent 名字

---

## 通知收件箱

- `inbox` 表（抄 Multica inbox_item）
- API：列表/已读/全部已读/归档
- `_create_inbox_item()` 复用函数
- 事件自动写入：Agent 消息、好友请求、告警
- 前端：铃铛+未读徽章+下拉面板+点击已读+全部已读

---

## 事件流增强

- 文本框块捕获（`claude_code.py` 补 `text` 类型 block 解析）
- `_publish_events` 文本截断 200→2000，新增 `text_full` 完整字段
- 展开详情面板：点击事件行展开完整内容（<pre> 可滚动）
- 分类：thinking(蓝)/tool_call(橙)/response(绿)/handoff(紫)
- 页面加载即启动 SSE，切换 tab 不断开

---

## Bug 修复

| Bug | 修复 |
|---|---|
| 聊天发消息卡 5-10 秒 | `socketio.emit` 后台线程化 + 工作线程 4→8 |
| 群聊消息重复显示 | onSocketMessage 去重 + HTTP 响应不再 push |
| Agent 消息显示 `[object Object]` | 旧聊天代码移除 + content 类型检查 |
| 全部 Agent 离线 | 采集器 `actual_last` 误判，改用 max(三源) |
| CPU 烧满 4000s | `_aggregate_daily_stats` 改为每天一次 |
| `[object Object]` 通讯录全离线 | `query_chat_contacts` online 判定加 idle/working |
| Token 仪表盘无数据 | `fetchChartsFromApi` 补 `updateCostChart` 调用 |
| 事件流暂停/清空按钮无效 | 加 onclick 事件 |
| CLI Agent 名显示为 "CLI Agent" | connect 时从 `/api/users` 解析真实名字 |
| 事件流必须切 tab 才启动 | 页面加载即连 SSE |
| 拓扑图打开 10 秒才显示 | connect 事件即时推送快照 |
| idle→offline 永不降级 | 加 `is_deep_stale and actual_last == hb` 条件 |

---

## 文件变更汇总

### 新建
- `myagentwatch/user.py`
- `myagentwatch-cli/`（完整项目）
- `changelog/2026-06-01_claude-code_天宇.md`

### 修改
- `collector.py` — 日聚合降频 + 活跃度逻辑 + SSE 文本扩展
- `app.py` — poll_interval 5s + threads 8 + 旧聊天移除
- `routes/chat_api.py` — `_emit_async` 后台线程
- `routes/api.py` — PAT/用户 API + 收件箱 API
- `queries.py` — chat_contacts online 判定
- `db.py` — users 表 + inbox 表 + migrations
- `config.yaml` — poll_interval 5s
- `pricing.py` — 补 deepseek-v4-pro/flash
- `sources/claude_code.py` — text block 解析
- `static/js/chat-wechat.js` — 去重 + sender_type 修正
- `static/js/app.js` — 清理死代码
- `static/js/event-stream.js` — 展开详情 + 分类 + 按钮事件
- `static/js/token-dashboard.js` — Chart.js 防护 + 趋势图联调
- `static/js/charts.js` — 补 cost chart + 可见性检查
- `static/js/constants.js` — working/blocked 颜色
- `static/css/chat-wechat.css` — 收件箱/事件流/Agent 消息/趋势图样式
- `static/index.html` — Token tab + 通知铃铛 + 事件流控制栏
