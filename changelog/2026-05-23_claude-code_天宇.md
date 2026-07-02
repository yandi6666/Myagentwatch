# 2026-05-23 — 对话日志系统完整实现

> **Agent**: Claude Code (deepseek-v4-pro)
> **用户**: 天宇

---

## 概述

实现了完整的多 Agent 统一对话日志系统，包括：
- 数据模型（Agent 全局唯一 ID + Turn + ContentBlock + HandoffInfo）
- 存储层（3 张新表 + 11 个索引 + FTS5 全文搜索）
- 采集层（LogAdapter 接口 + Claude Code 适配器）
- API 层（5 个新端点）
- 导出层（LogCompiler：Markdown / JSON）
- 前端（三栏布局日志查看器）

---

## 新增文件

| 文件 | 说明 |
|------|------|
| `sources/log_adapter.py` | AgentIdentity, Turn, ContentBlock, HandoffInfo 数据类 + LogAdapter 抽象接口 |
| `log_compiler.py` | Turn → Markdown / JSON 导出 |
| `static/css/log-viewer.css` | 日志查看器样式：5 色分类 + 错误高亮 + 来源标签 |
| `static/js/log-viewer.js` | 三栏日志查看器：Agent 树 + 日志流 + 详情面板 |

## 修改文件

| 文件 | 改动 |
|------|------|
| `db.py` | 新增 `conversation_turns` / `turn_content` / `agent_handoffs` / `collector_progress` 表 + 11 个索引 + FTS5 全文搜索 + 3 个同步触发器 |
| `sources/claude_code.py` | 实现 `LogAdapter` 接口：`agent_identity()` / `parse_turns()` / `_lines_to_turns()`，完整解析 thinking/tool_use/tool_result/response/handoff |
| `collector.py` | 新增 `_persist_turns()`（批量 executemany）、`_cleanup_old_logs()`（按 retention 清理）、`_existing_natural_keys()`（去重）|
| `queries.py` | 新增 `query_turns()` / `query_turn_tree()` / `query_turn_detail()` / `query_turn_trace()` / `query_turn_counts_by_agent()` |
| `routes/api.py` | 新增 `/api/logs/turns` / `/api/logs/tree` / `/api/logs/turn/<id>` / `/api/logs/trace/<id>` / `/api/logs/export` |
| `static/index.html` | 日志 tab 改为完整三栏布局 + 控制栏 |
| `static/js/app.js` | switchTab 中新增日志 tab 初始化 |

---

## 架构要点

### Agent 全局唯一 ID
```
{source_type}::{source_name}::{project_hash}::{agent_role}::{agent_name}::{model_id}
```

### 5 分类体系
```
思考(蓝) / 工具(橙) / 交互(紫) / 输出(绿) / 系统(灰)
```

### P0 全部就绪
- 索引 ✅    — 11 个索引覆盖高频查询
- 批量插入 ✅ — executemany 批量写入
- 整数主键 ✅ — INTEGER AUTOINCREMENT + natural_key UNIQUE
- 自动清理 ✅ — log_retention_days 配置生效
- 全文搜索 ✅ — FTS5 + ?q= 参数
- 错误高亮 ✅ — severity CSS class + 红色边框
- Trace ID ✅ — 跨 Agent 全链路追踪
- 去重保障 ✅ — natural_key UNIQUE + 内存批量检测

### P1 待后续
- 虚拟滚动 — 日志超 5000 条后 DOM 节点过多
- 树计数缓存 — 当前 COUNT 实时查询
- 采集进度持久化 — collector_progress 表已建，_persist_turns 已写，parse_turns 未用
