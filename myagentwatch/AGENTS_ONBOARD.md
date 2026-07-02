# MyAgentWatch — Agent 接入说明书

> 任何 Agent 工具，只需实现一个接口、写一行配置，即可出现在 MyAgentWatch 仪表盘上。

---

## 快速开始：3 分钟接入

### 你的工具属于哪种？

| 场景 | 接入方式 | 需要写代码？ |
|------|---------|------------|
| 我的工具用 **SQLite 存数据** | 用 `sqlite_agent` 适配器 → 改 config.yaml | **不用** |
| 我的工具输出 **JSON Lines 日志** | 用 `log_file` 适配器 → 改 config.yaml | **不用** |
| 我的工具格式特殊 | 写一个 30 行的 Python 类 | **用，约 5 分钟** |

---

## 方式一：SQLite 工具（零代码接入）

如果你的工具把 Agent 活动存到 SQLite 数据库里，只需要在 `config.yaml` 加一条：

```yaml
data_sources:
  - name: "my-tool"
    type: "sqlite_agent"
    db_path: "/path/to/tool.db"
    # 以下可选 — 如果跟 OpenCode 格式不同就填
    agent_query: "SELECT name, '' as model_id, '' as provider_id FROM agents"
    session_table: "tasks"       # 默认 "session"
    message_table: "messages"    # 默认 "message"
    time_column: "updated_at"    # 默认 "time_updated"
    enabled: true
```

`sqlite_agent` 适配器会自动：
1. 发现数据库中的 Agent（通过 `agent_query` 或解析 JSON 列）
2. 增量采集活动数据（Session/Message/Part）
3. 推送到仪表盘实时显示

### 支持的配置项

| 键 | 默认值 | 说明 |
|----|--------|------|
| `db_path` | *(必填)* | SQLite 数据库路径 |
| `agent_query` | 自动从 message 表 JSON 提取 | 发现 Agent 的 SQL |
| `session_table` | `session` | 会话表名 |
| `message_table` | `message` | 消息表名 |
| `part_table` | `part` | 动作/工具调用表名 |
| `time_column` | `time_updated` | 增量同步用的时间列 |
| `json_column` | `data` | 存 JSON 数据的列名 |
| `incremental` | `true` | 是否增量采集 |

### 示例：接入 n8n

```yaml
data_sources:
  - name: "n8n"
    type: "sqlite_agent"
    db_path: "~/.n8n/database.sqlite"
    agent_query: >
      SELECT DISTINCT json_extract(data, '$.workflowName') as name,
      'n8n' as agent_type, '' as model_id, '' as provider_id
      FROM execution_entity
    session_table: "execution_entity"
    message_table: "execution_data"
    json_column: "data"
    time_column: "startedAt"
    enabled: true
```

---

## 方式二：JSON Lines 日志（零代码接入）

如果你的工具输出 JSON Lines（每行一个 JSON 对象），配一行即可：

```yaml
data_sources:
  - name: "my-cli-tool"
    type: "log_file"
    path: "/var/log/my-tool/*.jsonl"
    format: "json_lines"
    agent_field: "agent"       # JSON 中存 Agent 名的字段
    model_field: "model"       # JSON 中存模型的字段
    enabled: true
```

### 日志格式要求

**JSON Lines (推荐，一行一个对象):**
```json
{"type":"task_start","agent":"strix_recon","model":"qwen-max","tool":"nmap","text":"开始端口扫描","timestamp":"2026-05-07T12:00:00"}
{"type":"task_complete","agent":"strix_recon","model":"qwen-max","tool":"nmap","text":"发现 3 个开放端口","timestamp":"2026-05-07T12:01:23"}
```

### 支持的配置项

| 键 | 默认值 | 说明 |
|----|--------|------|
| `path` | *(必填)* | 日志文件路径，支持 glob |
| `format` | `json_lines` | 格式 (json_lines / csv) |
| `agent_field` | `agent` | Agent 名字段 |
| `model_field` | `model` | 模型字段 |
| `text_field` | `text` | 文本内容字段 |
| `type_field` | `type` | 事件类型字段 |

### 示例：接入 Strix

Strix 运行时把输出重定向到 JSON Lines 文件：

```bash
# 运行 Strix 并输出结构化日志
strix --target ./app --non-interactive --json > ~/.strix/tasks/task_$(date +%s).jsonl
```

```yaml
data_sources:
  - name: "strix-security"
    type: "log_file"
    path: "~/.strix/tasks/*.jsonl"
    format: "json_lines"
    agent_field: "agent"
    model_field: "model"
    enabled: true

agent_meta:
  "strix_recon":
    display_name: "Strix 渗透侦察"
    group: "安全测试层"
```

---

## 方式三：自定义适配器（5 分钟写代码）

如果你的工具格式特殊，写一个适配器类：

### 第 1 步：创建 `sources/your_tool.py`

```python
"""MyTool data source."""

import time
from typing import List, Dict, Any

from . import register_source
from .base import SourceInterface, AgentInfo, CollectedData


@register_source("mytool")
class MyToolSource(SourceInterface):
    """从 MyTool 的 XXX 格式中采集 Agent 活动数据。"""

    def __init__(self, name: str, input_path: str, **kwargs):
        self.name = name
        self.input_path = input_path

    # ----- 必须实现 -----

    def connect(self) -> bool:
        """检查数据源是否可用，返回 True/False。"""
        import os
        return os.path.exists(self.input_path)

    def discover_agents(self) -> List[AgentInfo]:
        """从数据源中发现 Agent。

        返回 AgentInfo 列表，核心字段：
          - name: Agent 的内部名 (如 "plan", "strix_recon")
          - agent_type: Agent 类型 (如 "planner", "scanner")
          - model_id: 使用的模型名 (如 "deepseek-v4-pro")
          - provider_id: 模型提供商 (如 "deepseek")
        """
        agents = []
        # TODO: 解析你的数据源，填充 AgentInfo
        agents.append(AgentInfo(
            name="my_agent",
            agent_type="custom",
            model_id="my-model",
            provider_id="my-provider",
            last_seen_time=int(time.time() * 1000),
        ))
        return agents

    def collect(self, since_timestamp: int) -> CollectedData:
        """增量采集活动数据（自 since_timestamp 以来的增量）。

        返回 CollectedData，包含：
          - sessions: List[SessionInfo] — 会话记录
          - messages: List[MessageInfo] — 消息记录 (含 token/cost)
          - parts: List[PartInfo] — 工具调用/动作记录
          - last_sync_time: int — 本次采集的时间戳
        """
        data = CollectedData(last_sync_time=since_timestamp)
        # TODO: 解析数据，填充 SessionInfo/MessageInfo/PartInfo
        data.last_sync_time = int(time.time() * 1000)
        return data

    def health_check(self) -> Dict[str, Any]:
        """返回数据源健康状态。"""
        return {"name": self.name, "type": "mytool", "accessible": self.connect()}
```

### 第 2 步：在 `config.yaml` 中添加

```yaml
data_sources:
  - name: "my-tool-instance"
    type: "mytool"
    input_path: "/path/to/tool/output"
    enabled: true
```

### 第 3 步：添加 Agent 显示名（可选）

```yaml
agent_meta:
  "my_agent":
    display_name: "MyTool 主控"
    group: "自定义工具层"
```

**完成。** 重启 MyAgentWatch 后，你的 Agent 就会出现在仪表盘上。

---

## DataType 参考

### AgentInfo

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | Agent 内部名，用于匹配 config.yaml 的 agent_meta |
| `agent_type` | str | Agent 类型（原始标识） |
| `model_id` | str | 模型名称 |
| `provider_id` | str | 模型提供商 |
| `display_name` | str | 显示名（可留空，由 agent_meta 覆盖） |
| `group_name` | str | 分组名（可留空，由 agent_meta 覆盖） |
| `last_seen_time` | int | 最后活动时间 (millisecond epoch) |

### SessionInfo

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 会话 ID |
| `title` | str | 会话标题 |
| `parent_id` | str | 父会话 ID（子 Agent 派生） |
| `time_created` | int | 创建时间 (ms epoch) |
| `time_updated` | int | 更新时间 (ms epoch) |

### MessageInfo

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 消息 ID |
| `session_id` | str | 所属会话 ID |
| `agent` | str | 所属 Agent 名 |
| `model_id` | str | 调用的模型 |
| `tokens_input` | int | 输入 token 数 |
| `tokens_output` | int | 输出 token 数 |
| `tokens_reasoning` | int | 推理 token 数 |
| `cache_read` / `cache_write` | int | 缓存读/写 token |
| `cost` | float | API 调用成本 |
| `time_created` | int | 创建时间 (ms epoch) |

### PartInfo

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | Part ID |
| `message_id` | str | 所属消息 ID |
| `session_id` | str | 所属会话 ID |
| `part_type` | str | 类型: "text", "tool", "reasoning", "step-start", "step-finish" |
| `tool_name` | str | 工具名（如 "bash", "read"） |
| `tool_status` | str | 工具状态: "completed", "failed", "pending" |
| `text_content` | str | 文本内容 |
| `tokens_input/output/reasoning` | int | 本次调用的 token |
| `cost` | float | 本次调用成本 |
| `time_created` | int | 创建时间 (ms epoch) |

### CollectedData

| 字段 | 类型 | 说明 |
|------|------|------|
| `agents` | List[AgentInfo] | 发现的 Agent |
| `sessions` | List[SessionInfo] | 采集的会话 |
| `messages` | List[MessageInfo] | 采集的消息 |
| `parts` | List[PartInfo] | 采集的工具调用/动作 |
| `last_sync_time` | int | 本次同步时间戳 |

---

## 架构原理

```
┌───────── config.yaml ─────────┐
│ data_sources:                 │
│   - name: "strix"             │
│     type: "log_file"          │      ┌────────────────────┐
│     path: "~/.strix/*.jsonl"  │      │ SOURCE_REGISTRY    │
│                               │      │ {                  │
│   - name: "n8n"               │ ───> │   "log_file":      │
│     type: "sqlite_agent"      │      │     LogFileSource,  │
│     db_path: "~/.n8n/n8n.db"  │      │   "sqlite_agent":   │
│                               │      │     SQLiteAgentSrc, │
│ agent_meta:                   │      │   "opencode_db":    │
│   "strix_recon":              │      │     OpenCodeDBSrc,  │
│     display_name: "渗透侦察"   │      │   ...               │
│     group: "安全测试层"        │      │ }                   │
└───────────────────────────────┘      └─────────┬──────────┘
                                                  │
                                    Collector 按 type 匹配
                                    实例化 SourceInterface
                                                  │
                                          ┌───────▼────────┐
                                          │  仪表盘 Web UI  │
                                          │  (不感知来源)    │
                                          └────────────────┘
```

---

## 常见问题

**Q: 我接入后 Agent 在仪表盘上显示不了？**
A: 检查 (1) `discover_agents()` 是否返回了 Agent；(2) `connect()` 是否返回 `True`；(3) config.yaml 的 `name` 和 `agent_meta` 的 key 是否匹配。

**Q: 我的工具数据源不在这三种模式里怎么办？**
A: 写自定义适配器（方式三）。`@register_source` + `SourceInterface` ≈ 30 行代码。

**Q: 如何调试我的适配器？**
A: 启动后看日志：`python3 app.py 2>&1 | grep collector`，会打印每个数据源的连接和采集状态。
