# 2026-05-20 — 仪表盘合并 + 树列表重构 + 状态系统 + 群聊

> **Agent**: Claude Code (deepseek-v4-pro)
> **用户**: 天宇

---

## 一、仪表盘 & 拓扑合并

| # | 改动 | 文件 | 状态 |
|---|------|------|------|
| F1 | 仪表盘 + 拓扑合并为一个 tab（删「拓扑图」tab） | `index.html`, `app.js` | ✅ |
| F2 | 顶部导航右侧加搜索框 + 设置图标 + 用户头像 | `index.html`, `dashboard.css` | ✅ |
| F3 | 三栏布局：左侧集群总览 + 中间树列表 + 右侧告警/操作/资源 | `index.html` | ✅ |
| F4 | 树列表显示真实 Agent 名 + 可折叠 + 状态筛选 | `tree-list-view.js` | ✅ |
| F5 | 节点详情面板（选中后弹出：基本信息 + 操作按钮） | `tree-list-view.js` | ✅ |
| F6 | 主 agent 分组标识：独立色系左边框（不跟状态灯冲突） | `tree-list-view.js` | ✅ |
| F7 | 分组统计：在线 / 等待 / 错误 / 离线 | `tree-list-view.js` | ✅ |
| F8 | 右侧栏：实时告警 + 快捷操作 + 资源概览 + 趋势图表 | `index.html` | ✅ |
| F9 | 趋势图表底部通栏：Token消耗 + 成本累计 + 延迟趋势 | `index.html`, `charts.js` | ✅ |

## 二、Bug 修复

| # | 严重度 | 文件 | 描述 | 状态 |
|---|--------|------|------|------|
| B31 | 🔴 | `routes/ws.py` | `query_tree(conn)` 在 `with database()` 外执行 | ✅ |
| B32 | 🔴 | `collector.py` | FOREIGN KEY: session 无 agent 时 s_agent_id="" | ✅ |
| B33 | 🔴 | `sources/claude_code.py` | discover_agents 只取第一个 model，后续 model 找不到 | ✅ |
| B34 | 🔴 | `collector.py` | `_mark_stale_agents` UPDATE 后缺 `conn.commit()` — 事务回滚 | ✅ |
| B35 | 🔴 | `collector.py` | `source_healthy.get(name, True)` 默认 True — 断连来源误判健康 | ✅ |
| B36 | 🟡 | `queries.py` | `query_agents_active` 只查 `status='active'` — idle 被隐藏 | ✅ |
| B37 | 🟡 | `tree-list-view.js` | `BRANCH` 数组在 `renderTreeList` 内定义，`renderLeftSidebar` 先执行引用报错 | ✅ |
| B38 | 🟢 | `tree-list-view.js` | `border-l-4` 只设宽度缺 `border-left-style:solid` | ✅ |
| B39 | 🟢 | `config.yaml` | Claude Code 分组名 "AI编程助手" → "Claude Code" | ✅ |
| B40 | 🟢 | `sources/claude_code.py` | 子 agent 分组名硬编码 "AI编程助手" → "Claude Code" | ✅ |

## 三、状态系统重构

| 改动 | 说明 |
|------|------|
| 未活动 agent → idle | `_mark_stale_agents` 新增：从未有过活动日志的 agent 标为 idle（非 active） |
| 离线判断改用 `created_at` | 不再用每轮刷新的 `last_seen_time`，用固定不变的 `created_at` |
| 来源检查优先于活动检查 | 断开/移除/禁用的来源 → 直接 `source_removed`，不依赖超时 |
| 查询范围扩大 | `query_agents_active` → `status IN ('active','idle')`；状态卡片统计同步 |

## 四、群聊（Agent 协作频道）

| 改动 | 文件 | 状态 |
|------|------|------|
| 群聊广播模式：消息推给所有在线客户端 | `routes/api.py` | ✅ |
| 前端：发送者标签 + 自己/他人消息区分 | `app.js` | ✅ |
| 在线 Agent 列表：右侧栏实时显示 | `index.html`, `app.js`, `dashboard.css` | ✅ |
| 群聊输入自动启用（点 tab 后） | `app.js` | ✅ |

## 五、事件流独立化

- 底部 `#event-stream-bar` 删除，事件流内容移入独立「事件流」tab
- `#event-stream-bar` 140px 高度删除解决底部空白问题

## 六、安装脚本

| 文件 | 说明 |
|------|------|
| `install.bat` | 一键安装：venv + pip + 数据目录 |
| `myagentwatch.ps1` | PowerShell CLI：start/stop/restart/status/install |
| `myagentwatch.bat` | 终端入口：`myagentwatch` 全局启动 |

用法：
```powershell
myagentwatch              # 启动（首次自动安装）
myagentwatch stop         # 停止
myagentwatch restart      # 重启
```

## 七、后端

- `ws.py` 快照新增 `hourly_tokens` 字段供成本曲线图使用
- `api.py` 新增 `chat_message` SocketIO 事件处理器

## 八、其他

- `.claude/settings.local.json` 权限补充：Read/PowerShell/SendMessage/AskUserQuestion 等
- `dashboard.css` 大范围 CSS 重构：Tailwind 等价 class 全部用 `#panel-dashboard` 包裹
- `节点布局.html` / `新的拓补图布局.html` / `MyAgentWatch.pdf` — 用户设计稿参考
