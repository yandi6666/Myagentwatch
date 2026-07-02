# 2026-05-18 — 21 Bug 全量复审 + 修复方案

> **Agent**: Claude Code (deepseek-v4-pro)
> **用户**: 天宇

---

## 一、21 Bug 全景图

| # | 状态 | 严重度 | 文件 | 描述 |
|---|------|--------|------|------|
| B1 | ✅ 已修 | 🔴 | `sources/__init__.py` | 通用适配器未导入，`@register_source` 从未执行 |
| B2 | ✅ 已修 | 🔴 | `queries.py:116` | 拓扑 SQL 缺空格，拼接出 `''GROUP BY` 语法错误 |
| B3 | ✅ 已修 | 🔴 | `flow.js`, `dashboard.js` | 前端死代码 + dagre 依赖缺失 |
| B4 | ✅ 已修 | 🔴 | `alerting.py:39` | 告警引擎 `_get_metric_value()` 无 try/finally |
| B5 | ✅ 已修 | 🔴 | `db.py:get_connection()` | 外键约束仅在 init_db 启用，运行时未开启 |
| B6 | ✅ 已修 | 🔴 | `topology.js` | 拓扑图节点拖动失效 (4 个子问题) |
| B7 | ✅ 已修 | 🔴 | `collector.py:203` | `_persist_data` 缩进导致在已关闭连接上执行 SQL |
| B8 | ↩️ 撤回 | 🟢 | `alerting.py:116` | `cache_hit_pct` 公式 — token 级数据下正确，已撤回 |
| B9 | ✅ 已修 | 🟡 | `sqlite_agent.py`, `opencode_db.py` | f-string 拼接表名/列名，SQL 注入风险 |
| B10 | ✅ 已修 | 🟡 | `requirements.txt` | waitress 缺失 |
| B11 | ✅ 已修 | 🟡 | `db.py:init_db()` | init_db() 返回连接未关闭 |
| B12 | ✅ 已修 | 🟡 | `app.py` | `_daily_cleanup` / `_dedup_agents` 连接泄漏 |
| B13 | ✅ 已修 | 🔴 | `system.py`, `api.py` | Windows `disk_usage("/")` 崩溃 |
| B14 | ✅ 已修 | 🟡 | `app.py:185` | `socketio.wsgi_app` AttributeError 未捕获 |
| B15 | ✅ 已修 | 🟡 | `alerting.py:88-94` | `last_seen_delta` 语义偏差，MIN→MAX + 参数化查询 |
| B16 | ✅ 已修 | 🟡 | `config.py:64-69` | `_deep_merge` 对 list 类型全覆盖，模板 alert_rules 覆盖基配置 |
| B17 | ✅ 已修 | 🟢 | `db.py` | 无连接池，加 PRAGMA 缓存 + `execute_with_retry` |
| B18 | ✅ 已修 | 🟡 | `api.py` (12处) | API 路由 `get_connection()` 无 try/finally，异常时连接泄漏 |
| B19 | ✅ 已修 | 🟡 | `ws.py:17-44` | `build_snapshot()` 连接泄漏，改用 `database()` |
| B20 | ✅ 已修 | 🟢 | `claude_code.py:95-149` | `discover_agents()` 加 mtime 缓存，避免全量扫描 |
| B21 | ✅ 已修 | 🟢 | `event_bus.py:75-79` | `unsubscribe()` 时清理无订阅者的 ring buffer + slots |

> **统计**: 20 已修复 + 1 撤回 = 21 ✅ 全部处理完毕

---

## 二、待修 Bug 详细分析

### B9 🟡 SQL 注入风险 — `sqlite_agent.py` / `opencode_db.py`

**位置**:
- `sqlite_agent.py:67` `f"PRAGMA table_info({table})"`
- `sqlite_agent.py:126-131` `f"... FROM {self.message_table} ..."`
- `sqlite_agent.py:175-179` `f"... FROM {self.session_table} ..."`
- `sqlite_agent.py:199-201` `f"... FROM {self.message_table} ..."`
- `sqlite_agent.py:233-234` `f"... FROM {self.part_table} ..."`
- `opencode_db.py:42, 125-128, 147-149, 181-183` 同样模式

**根因**: 表名/列名来自 config.yaml 的用户输入，通过 f-string 直接拼入 SQL。虽然通常来自可信配置，但违反安全编码规范。

**修复方案**: 表名/列名使用白名单校验，或使用 `sqlite3` 的 `stmt.bind` 无法绑定标识符，需用正则 `\w+` 校验后拼接。**可修，5分钟。**

---

### B15 🟡 `last_seen_delta` 语义偏差 — `alerting.py:88-94`

**根因**: 
```python
"SELECT MIN(last_seen_time) as oldest FROM agents WHERE status = 'active'"
```
取的是"最旧 active agent 的 last_seen_time"，而非"最久无活动的 Agent"。如果所有 Agent 都很活跃，oldest 可能只有几秒，告警永远不触发。期望语义是"某个 Agent 多久没动静了"。

**修复方案**: 改为查询 `activity_log` 表中最新的时间戳：
```python
"SELECT (MAX(timestamp) - MIN(timestamp)) / 1000 as delta FROM activity_log"
```
或者按 Agent 逐个检查。**可修，10分钟。**

---

### B16 🟡 模板 alert_rules merge 覆盖 — `config.py:64-69`

**根因**: `_deep_merge` 对非 dict 值直接覆盖：
```python
else:
    base[key] = value  # template 的 alert_rules 直接替换整个列表
```
用户配置的 alert_rules 会被模板的 alert_rules 完全覆盖，而非合并。

**修复方案**: 对 `alert_rules` 做特殊处理（按 name 合并，template 同名规则覆盖，不同名规则追加）。**可修，10分钟。**

---

### B17 🟢 无连接池 — `db.py`

**根因**: 每次 `get_connection()` 新建 SQLite 连接，高并发下可能出现 `SQLITE_BUSY`。

**已缓解**: WAL 模式 + `timeout=10` 已配置，实际风险很低。SQLite 官方不建议连接池（WAL 模式已支持 1 writer + N readers）。

**修复方案**: 实现简单连接复用（维护单个写连接 + 线程本地读连接），或在 WAL 模式下此 bug 实质性风险极低，可标记为 WONTFIX。**修不修？低收益。**

---

### B18 🟡 API 路由连接泄漏 — `api.py` (约 10 处)

**位置**: 所有使用 `conn = get_connection()` + `conn.close()` 的路由：
- `api_agents()` line 45-48
- `api_sessions()` line 52-54
- `api_stats_overview()` line 58-61
- `api_health()` → collector 内部已安全
- `api_timeline()` line 84-90
- `api_stats_tokens()` line 95-103
- `api_stats_charts()` line 106-109
- `api_session_detail()` line 113-136
- `api_timeline_flow_session()` line 147-195
- `api_timeline_flow()` line 199-237
- `api_alerts()` line 241-246
- `api_alerts_resolve()` line 250-258

**根因**: 若 `conn.execute()` 间发生异常，`conn.close()` 被跳过。与 B4/B11/B12 同模式。

**修复方案**: 全部改用 `with database() as conn:`。**可修，15分钟。**

---

### B19 🟡 `ws.py` `build_snapshot()` 连接泄漏 — `ws.py:20-31`

**根因**: 同 B18 模式，`get_connection()` 后无异常保护，`conn.close()` 在 `return` 前但若 `query_overview_cards()` 等抛异常则泄漏。

**修复方案**: 改用 `with database() as conn:` 或 try/finally。**可修，2分钟。**

---

### B20 🟢 `discover_agents()` 性能 — `claude_code.py:95-149`

**根因**: 每次采集周期都读取全部 JSONL 文件全部行，仅用于发现 Agent。首次后可缓存。

**影响**: 会话数量多时（100+ JSONL），每次 discover 耗时数秒。Agent 信息极少变化。

**修复方案**: 缓存 Agent 列表（类级变量 + 文件 mtime 检查），仅在文件变化时重新扫描。**可修，15分钟。**

---

### B21 🟢 EventBus `_ring` 无限增长 — `event_bus.py:30-31`

**根因**: 
```python
self._ring: dict[str, deque] = {}
```
每 publish 一个新 event_type，`_ring` dict 就增加一个 key，永不删除。订阅者断开后 ring buffer 仍占用内存。

**影响**: 若 event_type 种类随时间增长（如动态 topic），内存缓慢泄漏。

**修复方案**: 在 `unsubscribe()` 或定期任务中清理无订阅者的 ring buffer。**可修，5分钟。**

---

## 三、修复可行性总结

| Bug | 难度 | 风险 | 建议 |
|-----|------|------|------|
| B9 | 低 | 低 | 立即修 |
| B15 | 低 | 低 | 立即修 |
| B16 | 低 | 中 | 立即修 |
| B17 | 中 | 中 | 评估后定（WAL 已缓解） |
| B18 | 低 | 低 | 立即修 |
| B19 | 低 | 低 | 立即修 |
| B20 | 低 | 低 | 立即修 |
| B21 | 低 | 低 | 立即修 |

**结论**: **8 个待修 Bug 全部可修。** 其中 7 个低难度、低风险，可快速批量修复。B17 (连接池) 在 WAL 模式下实际风险极低，可选修。

---

## 四、2026-05-18 修复清单

| # | 文件 | 改动 |
|---|------|------|
| B9 | `sqlite_agent.py`, `opencode_db.py` | 加 `_safe_ident()` 正则校验，所有 f-string 表名/列名经过白名单验证 |
| B15 | `alerting.py:88-94` | `MIN(last_seen_time)` → `MAX(? - last_seen_time)` 参数化查询，正确反映最长空闲 |
| B16 | `config.py:64-69` | `_deep_merge` 对 named dict list (如 alert_rules) 按 name 合并，非覆盖 |
| B17 | `db.py` | PRAGMA journal_mode 缓存（仅设一次）；加 `execute_with_retry()` 防 SQLITE_BUSY |
| B18 | `api.py` (12处) | 全部 `get_connection()` → `with database() as conn:` |
| B19 | `ws.py:17-44` | `build_snapshot()` 改用 `database()` context manager |
| B20 | `claude_code.py` | `discover_agents()` 加 `_agent_cache` + mtime 检查，目录未变时跳过全量扫描 |
| B21 | `event_bus.py:75-79` | `unsubscribe()` 时自动清理零订阅者的 ring buffer + slots |
| — | `alerting.py:116-126` | 顺便优化 `cache_hit_pct`：两次 SQL → 一次 |

**验证**: 19/19 测试通过 (`pytest tests/ -v`) ✅
