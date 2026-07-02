# MyAgentWatch 2.0 — 完整架构方案

> 融合 clawmetry 实时骨架 + 力导向拓扑图 + 配置驱动 + 自动发现 + 零假设启动 + 行业模板可选
> 参考案例：ClawLibrary-main / clawmetry-main / openclaw-office-main

---

## 一、技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| 后端 | **Flask 3 + Flask-SocketIO + APScheduler** | 已有，不改 |
| 实时流 | **SSE** (新增) + **WebSocket** (已有) | SSE 处理事件流/日志，WebSocket 推送仪表盘快照 |
| 前端 | **Vanilla JS + HTML/CSS** | 零构建步骤，单文件嵌入 |
| 力导向图 | **D3.js 7** (CDN，仅 force/selection/zoom/drag 4 模块) | 业界标准力模拟算法 |
| 图表 | **Chart.js** (已有) | 柱状图/折线图够用 |
| 图标 | **Font Awesome 6** (CDN 免费版) | 用户指定 |
| 存储 | **SQLite** (已有 myagentwatch.db) | 不改 |

---

## 二、前端模块划分

```
static/
├── index.html              ← 单页入口，所有 HTML 模板
├── css/
│   ├── dashboard.css       ← 全局主题、变量、卡片、玻璃拟态
│   ├── topology.css        ← 力导向图样式
│   ├── event-stream.css    ← 底部事件流样式
│   └── list-view.css       ← 列表/表格视图样式
└── js/
    ├── app.js              ← 主入口：WebSocket 连接、Tab 切换
    ├── dashboard.js        ← 顶部状态栏 + 统计卡片
    ├── topology.js         ← D3 force-directed graph (核心新模块)
    ├── node-detail.js      ← 右侧节点详情面板
    ├── event-stream.js     ← 底部实时事件流
    ├── list-view.js        ← 按分组折叠的列表视图
    ├── config-panel.js     ← 配置面板
    ├── group-chat.js       ← Agent 群聊面板
    ├── charts.js           ← Chart.js 图表 (已有)
    ├── logs.js             ← 日志视图 (已有)
    └── ws-client.js        ← WebSocket 客户端封装
```

---

## 三、页面布局结构

```
┌──────────────────────────────────────────────────────────┐
│  TopBar: [📊仪表盘] [🔗拓扑图] [📋列表] [⚙️配置] [💬群聊] [📋日志]  │
├──────────────────────────────────────────────────────────┤
│  StatusStrip: 🟢12活跃 │ 📊301K Token │ ✅98% │ 💰$0.85  │
├───────────────────────┬──────────────────────────────────┤
│                      │  NodeDetailPanel                  │
│  拓扑图 (D3 Force)    │  ┌────────────────────────┐     │
│                      │  │ Agent: plan              │     │
│   🟢 plan ── 🟢 build │  │ 模型: deepseek-v4-pro   │     │
│    │ ╲       │       │  │ Token: 45.2K (实时)     │     │
│    │  ╲     🟡 expl  │  │ 延迟: 3.2s (实时)       │     │
│    │   ╲     │       │  │ 成本: $0.43 (实时)       │     │
│   🟢 maint 🔴 err    │  │ 📊 Token 趋势           │     │
│                      │  │ 📋 最近活动              │     │
│  🖱拖拽  🖱缩放  🖱点击│  └────────────────────────┘     │
├───────────────────────┴──────────────────────────────────┤
│  EventStream: 🟢[20:00:24] plan 完成任务, Token 12.5K    │
│              🔵[20:00:23] build 正在生成代码...          │
└──────────────────────────────────────────────────────────┘
```

### Tab 切换方式
- CSS class toggle：点击 tab 隐藏/显示对应面板
- 所有 tab 状态通过 WebSocket 持续接收数据，切过去立即渲染

---

## 四、核心组件详解

### 4.1 力导向拓扑图 (`topology.js`)

**技术选型：D3.js forceSimulation**

不使用 D3 全套，只用 4 个模块：
```
d3-force        ← 力模拟引擎
d3-selection    ← DOM 操作
d3-zoom         ← 缩放/平移
d3-drag         ← 拖拽
```

**数据模型（通过 WebSocket 推送）：**
```json
{
  "nodes": [
    {
      "id": "plan",
      "display_name": "OpenCode 主控",
      "group": "代码生成与系统维护层",
      "status": "active",
      "tokens_total": 45200,
      "tokens_1h": 3800,
      "latency_ms": 3200,
      "cost": 0.43,
      "configured": true,
      "model": "deepseek-v4-pro",
      "last_seen": 1778162789906
    }
  ],
  "edges": [
    {
      "source": "plan",
      "target": "build",
      "call_count": 87,
      "parent_child": true
    }
  ]
}
```

**节点视觉规则：**

| 属性 | 映射 |
|------|------|
| 半径 | `8 + tokens_total / 1000` px，上限 40px |
| 颜色 | active=#22c55e, idle=#f59e0b, thinking=#3b82f6, error=#ef4444, offline=#6b7280 |
| 虚线边框 | `configured === false` 时 `stroke-dasharray` |
| 脉冲 | thinking 状态时 CSS `@keyframes agent-pulse` |
| 标签 | display_name，字号 10px |

**连线视觉规则：**

| 属性 | 映射 |
|------|------|
| 粗细 | `1 + call_count / 20` px，上限 6px |
| 颜色 | 默认 #60a5fa，父子关系虚线 |
| 透明度 | 0.3 ~ 0.8 按 call_count 映射 |

**交互：**
- 拖拽节点 → D3 drag behavior
- 缩放/平移 → D3 zoom behavior
- 单击节点 → 右侧 NodeDetailPanel 打开
- 双击节点 → 聚焦该节点及其邻域

**力模拟参数：**
```js
forceSimulation(nodes)
  .force("link", forceLink(edges).distance(120))
  .force("charge", forceManyBody().strength(-400))
  .force("center", forceCenter(width/2, height/2))
  .force("collide", forceCollide(40))
```

### 4.2 顶部状态栏 (`dashboard.js`)

纯 WebSocket 推送，不轮询。每收到 `stat_snapshot` 事件直接更新 DOM。

```json
{
  "type": "stat_snapshot",
  "active_agents": 12,
  "total_tokens_today": 301200,
  "success_rate": 98.3,
  "cost_today": 0.85
}
```

### 4.3 右侧节点详情面板 (`node-detail.js`)

点击拓扑图节点后，从 WebSocket 缓存中读取该节点数据渲染。

```
┌──────────────────────┐
│ 🟢 plan              │
│ OpenCode 主控         │
│ 分组: 代码生成与系统维护层 │
│ 模型: deepseek-v4-pro │
│ ──────────────────── │
│ Token 消耗: 45,200    │
│ 最近1h: 3,800         │
│ 延迟: 3.2s            │
│ 成本: $0.43           │
│ ──────────────────── │
│ 📊 Token 趋势 (迷你折线)│
│ 📋 最近活动 (5 条)     │
│  🔧 bash: 完成        │
│  📖 read: 完成        │
│  ✏️ edit: 完成        │
└──────────────────────┘
```

### 4.4 底部事件流 (`event-stream.js`)

SSE 流驱动的实时滚动日志。新事件从顶部插入，自动滚动。

```json
{
  "type": "event",
  "level": "info",
  "timestamp": "20:00:24",
  "agent": "plan",
  "message": "完成决策任务，Token消耗 12,500",
  "icon": "✅"
}
```

每条事件颜色编码：info=灰色, warn=黄色, error=红色。

### 4.5 列表视图 (`list-view.js`)

按 group 分组，每组可折叠/展开。WebSocket 实时刷新。

```
┌─ 代码生成与系统维护层 [展开 ▼] ─────────────────────┐
│ 状态 │ Agent            │ 模型       │ Token  │ 延迟 │ 成本 │ 活跃  │
│ 🟢   │ OpenCode 主控     │ deepseek   │ 45.2K  │ 3.2s │$0.43 │ 20:00 │
│ 🟢   │ OpenCode 构建     │ deepseek   │ 28.7K  │ 2.1s │$0.31 │ 20:00 │
│ 🟡   │ OpenCode 探索     │ deepseek   │    0   │   -  │$0.00 │ 18:45 │
└──────────────────────────────────────────────────────────┘
```

未配置 Agent 的 group 显示为"默认 (未配置)"，字段未知时显示"(未知)"，虚线边框表示。

---

## 五、后端模块划分

```
myagentwatch/
├── app.py                      ← Flask + SocketIO 入口
├── config.yaml                 ← 配置文件 + 行业模板
├── templates/                  ← 行业模板 (新增)
│   ├── quant_trading.yaml
│   ├── web_dev.yaml
│   └── default.yaml
├── myagentwatch/
│   ├── __init__.py
│   ├── db.py                   ← SQLite 管理
│   ├── config.py               ← config.yaml 加载 + 模板叠加
│   ├── collector.py            ← 采集调度器 (已有)
│   ├── alerting.py             ← 告警引擎 (已有)
│   ├── event_bus.py            ← SSE 事件总线 (新增)
│   ├── sources/
│   │   ├── __init__.py         ← SOURCE_REGISTRY (已有)
│   │   ├── base.py             ← SourceInterface (已有)
│   │   ├── opencode_db.py      ← OpenCode DB (已有)
│   │   ├── opencode_log.py     ← OpenCode 日志 (已有)
│   │   ├── sqlite_agent.py     ← 通用 SQLite (已有)
│   │   ├── log_file.py         ← 通用日志 (已有)
│   │   └── system.py           ← 系统资源 (已有)
│   ├── templates/              ← 模板管理 (新增)
│   │   └── template_engine.py
│   └── AGENTS_ONBOARD.md       ← 已有
```

### 5.1 SSE 事件总线 (`event_bus.py`)

Server-to-client 实时事件发布/订阅，clawmetry 风格：

```python
class EventBus:
    _subscribers: Dict[str, List[queue.Queue]] = {}
    
    def publish(self, event_type: str, data: dict):
        for q in self._subscribers.get(event_type, []):
            q.put(data)
    
    def sse_stream(self, event_type: str):
        """Flask SSE generator with MAX 20 concurrent clients."""
```

### 5.2 行业模板引擎 (`template_engine.py`)

```python
def load_template(name: str) -> dict:
    """Load a named industry template from templates/."""

def merge_config(base: dict, template: dict) -> dict:
    """Deep merge template into base config, template wins."""
```

模板文件示例 (`templates/quant_trading.yaml`)：
```yaml
template: quant_trading
display_name: "量化交易监控"

agent_meta:
  "plan":    { display_name: "基金经理",   group: "最高决策层", color: "#3b82f6" }
  "build":   { display_name: "策略开发",   group: "代码生成层", color: "#22c55e" }
  "explore": { display_name: "研报分析",   group: "情报收集层", color: "#a855f7" }

alert_rules:
  - name: "extreme_cost"
    metric: "session_cost"
    condition: ">"
    threshold: 50.0
    level: "critical"
```

配置时只需改一行：
```yaml
template: "quant_trading"   # 或不写，用默认通用模板
```

---

## 六、数据库设计变更

现有 `myagentwatch.db` 表不变。新增两张表：

```sql
-- 拓扑关系表：Agent 之间的父子/调用关系
CREATE TABLE agent_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_agent_id TEXT NOT NULL,
    target_agent_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,     -- parent_child | tool_call | handoff
    call_count INTEGER DEFAULT 1,
    last_seen INTEGER,
    UNIQUE(source_agent_id, target_agent_id, relation_type)
);

-- 行业模板配置
CREATE TABLE template_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT UNIQUE NOT NULL,
    config_json TEXT NOT NULL,
    active INTEGER DEFAULT 0,
    applied_at INTEGER
);
```

---

## 七、数据采集与子 Agent 追踪

### 7.1 数据流架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ opencode.db  │     │ log files    │     │ system       │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────┐
│                Collector.cycle()                      │
│  1. 增量采集 raw data                                │
│  2. 持久化到 myagentwatch.db                         │
│  3. 构建拓扑关系 (agent_relationships)                │
│  4. 评估告警规则                                     │
│  5. 推送到 EventBus                                  │
└──────────────────────┬───────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     WebSocket    SSE stream    SSE stream
   (stat_snapshot) (topology)  (event_log)
```

### 7.2 子 Agent 识别

| 追踪维度 | 数据来源 | 方法 |
|----------|---------|------|
| 父 Agent 发现 | `message.data.agent` | 从 opencode.db 的 message 表 JSON 提取 |
| 子 Agent 派生 | `session.parent_id` | 非空 parent_id → 该会话是子 Agent |
| 调用关系 | `part.data.callID` + tool name `"task"` | task 工具被调用时，callID 对应的 session 即为子 Agent |
| 父子链 | `session` 表 parent_id 递归 | 构建完整的派生树 |

### 7.3 拓扑关系 SQL

```sql
-- 父 Agent → 子 Agent 关系
SELECT DISTINCT 
    a1.display_name as source_name,
    a2.display_name as target_name,
    COUNT(*) as call_count
FROM sessions s1
JOIN sessions s2 ON s2.parent_id = s1.id
JOIN agents a1 ON a1.id LIKE (SELECT agent_id FROM sessions WHERE id = s1.id) || '%'
JOIN agents a2 ON a2.id LIKE (SELECT agent_id FROM sessions WHERE id = s2.id) || '%'
GROUP BY s1.agent_id, s2.agent_id
```

---

## 八、实时性方案（完整版）

| 组件 | 更新机制 | 频率 |
|------|---------|------|
| 顶部状态栏 | WebSocket `stat_snapshot` | 每 2s 推送 |
| 拓扑图 | WebSocket `topology_update` | Agent 拓扑变化时推送 |
| 节点详情 | WebSocket `agent_detail` | 选中节点时订阅，2s 推送 |
| 列表视图 | WebSocket `agent_list` | 每 2s 推送 |
| 底部事件流 | SSE `/api/events/stream` | 新事件即时推送 |
| 日志流 | SSE `/api/logs/stream` | 新日志行即时推送 |
| 群聊 | WebSocket `chat_message` | 即时收发 |

**WebSocket 事件类型汇总：**

| 事件 | 方向 | 内容 |
|------|------|------|
| `stat_snapshot` | S→C | 顶部卡片数据 + 所有 Agent 列表 |
| `topology_update` | S→C | 拓扑图 nodes + edges |
| `agent_detail` | S→C | 单个 Agent 详情 |
| `event_stream` | S→C | 事件流条目 |
| `log_line` | S→C | 日志行 |
| `alert_event` | S→C | 告警 |
| `chat_message` | S↔C | 群聊消息 |
| `config_updated` | S→C | 配置变更通知 |

---

## 九、配置文件

```yaml
# MyAgentWatch 2.0 配置
version: 2

# 行业模板 (可选)
template: "default"

# 数据源定义
data_sources:
  - name: "main-opencode"
    type: "opencode_db"
    db_path: "~/.local/share/opencode/opencode.db"
    log_dir: "~/.local/share/opencode/log"
    enabled: true
  # 多数据源示例：
  # - name: "strix"
  #   type: "log_file"
  #   path: "~/.strix/tasks/*.jsonl"
  #   format: "json_lines"
  #   agent_field: "agent"
  #   enabled: true

# Agent 元数据 (自动发现 + 配置覆盖)
agent_meta:
  "plan":
    display_name: "OpenCode 主控"
    group: "代码生成与系统维护层"
    color: "#3b82f6"
  "build":
    display_name: "OpenCode 构建"
    group: "代码生成与系统维护层"
    color: "#22c55e"

# 拓扑图配置
topology:
  force_strength: -400
  link_distance: 120
  node_size_min: 8
  node_size_max: 40
  collision_radius: 40
  show_labels: true
  animate_thinking: true

# 告警规则
alert_rules:
  - name: "agent_idle"
    description: "Agent 超时无活动"
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

# 轮询配置
poll_interval: 2
```

---

## 十、前端 UI 设计系统

### 颜色
```css
:root {
    --bg-primary: #1a1a2e;
    --bg-card: #16213e;
    --bg-card-hover: #1e2d50;
    --accent: #0f3460;
    --accent-bright: #e94560;
    --text-primary: #eaeaea;
    --text-muted: #8892b0;
    --border: rgba(255,255,255,0.08);
    --glass-bg: rgba(22,33,62,0.7);
    --glass-blur: blur(10px);

    /* 状态色 */
    --status-active: #22c55e;
    --status-idle: #f59e0b;
    --status-thinking: #3b82f6;
    --status-error: #ef4444;
    --status-offline: #6b7280;
}
```

### 玻璃拟态
```css
.panel {
    background: var(--glass-bg);
    backdrop-filter: var(--glass-blur);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 4px 30px rgba(0,0,0,0.3);
}
```

### 图标
- Font Awesome 6 Free CDN
- 激活=中实心圆, 错误=圆叉, 等待=中空圆, 思考=中脑, 离线=虚线圆

---

## 十一、参考案例借鉴清单

| 借鉴来源 | 借什么 |
|----------|--------|
| **clawmetry** | SSE 实时流 + 模块化 Blueprint + 零构建步骤 + 可插拔数据源 + 粒子动画思路 |
| **OpenClaw Office** | 力导向拓扑布局 + WebSocket 状态驱动视觉 + SVG avatar 生成 |
| **ClawLibrary** | 玻璃拟态 CSS 变量 + 属性驱动配色 (data-tone) + CSS backdrop-filter |

---

## 十二、实施路径（7 步）

| 序号 | 内容 | 预估 |
|------|------|------|
| 1 | 重构前端 Tab 导航 + 玻璃拟态 CSS 主题 + Font Awesome 集成 | 1h |
| 2 | D3 力导向拓扑图 (`topology.js`) | 2h |
| 3 | 节点详情面板 (`node-detail.js`) | 1h |
| 4 | SSE 事件总线后端 (`event_bus.py`) + 底部事件流前端 (`event-stream.js`) | 1.5h |
| 5 | 列表视图（分组折叠）(`list-view.js`) | 1h |
| 6 | 行业模板引擎 (`template_engine.py`) + 模板文件 | 1h |
| 7 | 子 Agent 追踪 + 拓扑关系持久化 + 联调 | 1h |

| 总计 | **约 8.5 小时** |
|------|---------------|

---

> 方案保存位置：`/home/openclaw/Desktop/MyAgentWatch-2.0-架构方案.md`
> 审查完后说「开始执行」即可进入实现阶段。
