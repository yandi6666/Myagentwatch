# 2026-05-19 — Bug修复 + 拓扑3.1 + 画笔拖拽

> **Agent**: Claude Code (deepseek-v4-pro)
> **用户**: 天宇

---

## 一、Bug 修复

| # | 严重度 | 文件 | 描述 | 状态 |
|---|--------|------|------|------|
| B28 | 🔴 | `routes/ws.py:32` | `query_tree(conn)` 在 `with database()` 块外执行，连接已关闭 → "Cannot operate on a closed database" | ✅ |
| B29 | 🔴 | `collector.py:228` | session 无对应 agent 时 `s_agent_id=""` → FOREIGN KEY constraint failed | ✅ |
| B30 | 🔴 | `sources/claude_code.py` | `discover_agents()` 每个 session 只取第一条 assistant 消息的 model，后续不同 model 的消息找不到 agent → FK 失败 | ✅ |

### 详细

**B28** — `routes/ws.py:32`
- `query_tree(conn)` 移到 `with database() as conn:` 块内，连接关闭前执行

**B29** — `collector.py:228`
- session 无 message → session_agent_map 无对应 entry → s_agent_id 为空字符串
- 加 `if not s_agent_id: continue` 跳过无 agent 的 session

**B30** — `sources/claude_code.py:_parse_session_lines`
- 每条 assistant 消息的 model 可能不同（子 agent 用不同模型）
- 在 `_parse_session_lines` 中遇到新 model 时动态追加到 `data.agents`
- agents 数从 3 → 10（正确覆盖所有变体）

---

## 二、拓扑图 3.1 重设计

| 文件 | 改动 |
|------|------|
| `tree-layout.js` | 方向 TB→LR（左→右），卡片 300×110，边坐标适配 LR |
| `tree-view.js` | 完全重写：根→分组→Agent 三层结构，贝塞尔曲线，分级边颜色 |
| `dashboard.css` | 白色卡片+顶部分支色条+状态点+深色根节点+省略号样式 |

### 设计对齐（参照用户 `节点布局.html` + `MyAgentWatch.pdf`）

| 要素 | 实现 |
|------|------|
| 根节点 | 左侧深色圆角矩形 "MyAgentWatch" |
| L0→L1 连线 | 彩色粗线（红 #ef6b6b / 橙 #f56c42 / 青绿 #5dc49b），按分组分支 |
| L1→L2 连线 | 黑色细线 (#374151, 1.2px) |
| 卡片 | 白底+顶部4px分支色条+名称+要求描述+状态点行 |
| 状态点 | 🟢在线 🟡等待 🔴错误 ⚫离线 |
| 底部省略号 | `.........` 灰字，表无限扩展 |
| 分组 | 按 `agent_meta.group` 自动分组，动态分支数 |

---

## 三、画笔 + 节点拖拽

| 功能 | 实现 |
|------|------|
| 节点拖拽 | d3.drag() 绑定每个节点，拖拽时连线自动跟随 |
| 画笔标注 | 工具栏「画笔」按钮切换，SVG overlay 自由绘制红色线条 |
| 清除标注 | 「清除」按钮一键删除所有画笔路径 |
| 互斥 | 画笔激活时拖拽禁用，关闭画笔恢复拖拽 |
| 工具栏 | `index.html` 拓扑面板顶部新增按钮行 |

---

## 四、权限配置

- `.claude/settings.local.json`：补充 `Read`/`PowerShell`/`SendMessage`/`AskUserQuestion`/`EnterPlanMode` 等全部常用工具 allow
- 解决每次操作弹确认框的问题
