# 2026-05-18 R2 — 仪表盘审查 + Agent 存活监控

> **Agent**: Claude Code (deepseek-v4-pro)
> **用户**: 天宇

---

## 一、新增 Bug (仪表盘审查发现)

| # | 严重度 | 文件 | 描述 | 状态 |
|---|--------|------|------|------|
| B22 | 🟡 | `node-detail.js:38-39` | 右侧面板"最近活动"永远是"等待数据..." | ✅ |
| B23 | 🟡 | `app.js:105`, `event-stream.js:58` | 事件流只显示 event_type 不解析 data 字段 | ✅ |
| B24 | 🟡 | `node-detail.js` | 右侧面板缺 Token趋势图 + 调用链路图 | 🔵 延后 |
| B25 | 🟢 | `node-detail.js:34` | 延迟显示 ms → 布局图期望 s | ✅ |
| B26 | 🟢 | `topology.js` + `collector.py` | thinking 脉冲动画永不触发 | 🔵 延后 |
| B27 | 🔴 | `collector.py` | Agent 挂掉 status 永远 active | ✅ |

## 二、功能增强

| # | 功能 | 状态 |
|---|------|------|
| F1 | Agent 自动离线 (last_seen > N秒 → offline) | ✅ |
| F2 | 区分离线原因 (source_disconnected / source_disabled / agent_idle) | ✅ |
| F3 | Webhook 通知 (告警触发 → HTTP POST JSON) | ✅ |
| F4 | 浏览器通知 (Notification API) | ✅ |
| F5 | 拓扑图 forceX 按 group 分群 | ✅ |
| F6 | 列表搜索框 + 来源筛选下拉 | ✅ |

---

## 三、详细改动

### B22 — 右侧面板"最近活动"
- `node-detail.js`: 新增 `populateRecentActivity()` + `parseEventDesc()`
  - 从 `window.lastSnapshot.activity_log` 按 agent_id 过滤最近5条
  - 解析 event_type + data JSON → 可读描述 (🔧工具调用 / 💬文本 / 🧠推理)
  - 延迟 >1s 显示秒，<1s 显示毫秒
  - 离线 Agent 显示离线原因行

### B23 — 事件流描述
- `collector.py:_publish_events()`: event payload 加 `detail` / `model_id` / `tool_name` / `tool_status` 字段
- `event-stream.js:addOneEvent()`: 根据 event_type 生成可读描述
  - `assistant` → "🤖 回复 — 模型: xxx, tokens_in: xxx"
  - `tool_xxx` → "🔧 xxx [completed]"
- `app.js:updateLogStream()`: 新增 `parseLogDesc()` 解析 activity_log.data JSON

### B25 — 延迟单位自适应
- `node-detail.js` / `list-view.js`: `>= 1000ms` → `x.xs`，`< 1000ms` → `xms`

### B27 + F1 + F2 — Agent 自动离线
- `collector.py`: 新增 `_mark_stale_agents()`
  - `agent_stale_timeout` (默认 300s) 配置项
  - 超时 Agent → `status='offline'`, metadata 写入离线原因
  - 离线原因: `source_disconnected` / `source_disabled` / `source_removed` / `agent_idle`
  - 新数据到达时自动恢复 `active` (INSERT OR REPLACE)
  - `source_healthy` dict 追踪每个数据源的连接状态
- `config.py`: 默认配置加 `agent_stale_timeout: 300`

### F3 — Webhook 通知
- `alerting.py`: 新增 `_send_webhook()` 方法
  - 告警规则支持 `webhook_url` 字段
  - 触发时 POST JSON payload (alert name/level/value/threshold/timestamp)
  - 5s 超时，失败仅日志不阻塞
- 兼容钉钉/飞书/企业微信等 (通用 JSON 格式)

### F4 — 浏览器通知
- `app.js`: `alert_event` 处理中调用 `Notification` API
  - 首次加载请求 `Notification.permission`
  - tag 防重复弹窗

### F5 — 拓扑图 forceX 分群
- `topology.js`: `_updateSimulation()` 中按 group_name 计算 forceX 锚点
  - 同分组 Agent 被磁力拉到同一 X 列
  - `strength(0.08)` 轻柔吸附，不影响拖拽

### F6 — 列表搜索筛选
- `index.html`: 列表 tab 顶部加搜索框 + 来源下拉
- `list-view.js`:
  - `updateListView()` 新增搜索/筛选过滤逻辑
  - `_sourceLabel()` 返回来源标签 HTML (OpenCode/Claude/System)
  - `_populateSourceFilter()` 动态填充来源下拉
  - `DOMContentLoaded` 监听搜索框 input 和下拉 change
- `dashboard.css`: 新增 `.src-tag` 样式 (OpenCode 绿色 / Claude 紫色)

---

## 四、验证

- 19/19 测试通过 ✅
- Python 编译检查全通过 ✅

---

## 五、两轮合并统计

| | R1 | R2 | 合计 |
|---|-----|-----|------|
| Bug 修复 | B9, B15-B21 (8) | B22, B23, B25, B27 (4) | **12** |
| 功能增强 | — | F1-F6 (6) | **6** |
| 延后 | — | B24, B26 (2) | **2** |
| 改到文件 | 10 | 10 | **14** (去重) |

---

## 六、R3 — 拓扑聚合/展开

### 问题
每个来源不同形状解决了 "分不清" 但没解决 "太多了"。50+ Agent 力导向图变成毛线球。

### 方案
**三层缩放策略的第 1 层**：拓扑图默认按来源聚合。

### 改动 (`topology.js` 完全重写)

| 功能 | 实现 |
|------|------|
| 聚合模式 | 默认 >8 Agent 按 source 分组，一个来源一个聚合节点 |
| 展开 | 点击聚合节点 → 该来源的所有 Agent 展开显示 |
| 收拢 | 双击空白区域 → 全部收拢回聚合视图 |
| 自动模式 | ≤8 Agent 自动全部展开（小型拓扑无需聚合） |
| 聚合节点 | 形状=来源形状，大小∝Agent数量，标签="Claude Code (12)" |
| 聚合边 | 来源间有任意连接即显示一条加权边 |

### 视觉效果
```
  默认聚合视图:                          展开后:
  ┌──────────────┐                     ◆ Claude Code
  │ ⬡ OpenCode   │──┐                  ◆ Claude Code
  │    (35)      │  │   双击空白         ⬡ OpenCode (35)
  └──────────────┘  │   ←──────▶       ⬡ OpenCode
                    ▼                    ◆ Claude Code
  ┌──────────────┐                       ⬡ OpenCode
  │ ◆ ClaudeCode │  ← 紫边菱形
  │    (12)      │
  └──────────────┘
```

### 相关文件
- `topology.js`: 重写，+`_buildAggregateTopo()`, +`_computeView()`, +`_toggleSource()`
- `dashboard.css`: +`.topo-node.aggregate` 样式 (阴影+粗体)
- `index.html`: 图例更新，加操作提示

---

## 七、R4 — 拓扑完全重做 (2026-05-19)

### 竞品分析结论
OCWatch / claude-watch / ClawView 三个项目**没有一个用力导向图**。OCWatch 用确定性树布局+XY Flow，claude-watch 用纯文本树。

### 重做内容

| 旧 | 新 |
|----|-----|
| `topology.js` (D3 force simulation) | `tree-layout.js` (Buchheim 算法) + `tree-view.js` (D3 zoom/foreignObject) |
| SVG 彩色圆/六边形/菱形节点 | SVG foreignObject 320×140px HTML 信息卡片 |
| 节点位置每次刷新跳动 | 确定性树布局，位置永不改变 |
| 聚合/展开收拢 | 聚焦模式：点击卡片 → 非相关节点 dim 28% |
| 形状区分来源 | 卡片左侧色条 + 来源徽章区分 |

### 卡片结构
```
┌──────────────────────────────────┐
│ [OpenCode]           🟢 工作中   │ ← 来源徽章 + 状态点
├──────────────────────────────────┤
│ OpenCode 主控                    │ ← Agent 名
│ 编辑 collector.py                │ ← 当前动作
│ 🔧 bash [completed]              │ ← 工具调用
├──────────────────────────────────┤
│ deepseek  in:12.3K out:4.2K $0.43│ ← 模型/Token/成本
└──────────────────────────────────┘
```

### 新增文件
- `static/js/tree-layout.js` — Buchheim 确定性树布局引擎
- `static/js/tree-view.js` — D3 foreignObject 卡片渲染 + 聚焦模式

### 后端改动
- `queries.py`: 新增 `query_tree()` — 递归构建 sessions→agents 树形 JSON
- `ws.py`: `build_snapshot()` 加 `tree` 字段

### 验证
19/19 测试通过 ✅
