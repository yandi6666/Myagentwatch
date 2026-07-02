"""LogAdapter — 统一对话日志适配器接口。

每个数据源实现此接口，将原生日志格式翻译为统一的 Turn 流。
跨来源、多 Agent 对话日志的基础抽象层。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentIdentity:
    """全局唯一 Agent 身份标识。

    ID 格式: {source_type}::{source_name}::{project_hash}::{agent_role}::{agent_name}::{model_id}
    """

    source_type: str          # claude_code / opencode / n8n / custom
    source_name: str          # 用户命名的实例名，如 "我的桌面Claude"
    project_hash: str         # 项目路径的短哈希
    agent_role: str           # main / subagent / workflow / tool
    agent_name: str           # Agent 名称
    model_id: str             # 模型标识

    @property
    def global_id(self) -> str:
        return f"{self.source_type}::{self.source_name}::{self.project_hash}::{self.agent_role}::{self.agent_name}::{self.model_id}"


@dataclass
class ContentBlock:
    """Turn 内的一个内容块 — thinking 文本 / 工具调用 / 回复文本等。"""

    block_type: str           # thinking / tool_input / tool_output / response_text / error_output
    mime_type: str = "text/plain"
    content: str = ""         # 完整内容，不截断
    tool_name: str | None = None
    tool_call_id: str | None = None   # 配对 tool_input 和 tool_output
    char_count: int = 0

    def __post_init__(self):
        if self.char_count == 0 and self.content:
            self.char_count = len(self.content)


@dataclass
class HandoffInfo:
    """Agent 间交接的详细信息。"""

    from_agent_id: str        # 派发方全局 ID
    to_agent_id: str          # 接收方全局 ID
    to_session_id: str        # 子 Agent 的 session
    subagent_type: str = ""   # Explore / Plan / general-purpose / ...
    prompt: str = ""          # 派发提示词
    result: str | None = None # 返回结果（完成时填充）
    status: str = "pending"   # pending / running / completed / error


@dataclass
class Turn:
    """一次对话回合 — 所有来源统一为此结构。

    前端展示时按 phase 映射到 5 个分类：
      thinking / tool_call|tool_result → 工具 / handoff → 交互
      response|instruction → 输出 / heartbeat|error|source_status → 系统
    """

    turn_id: str              # 逻辑唯一键: {agent_id}::{session_id}::{seq}
    natural_key: str          # 全局去重键，同 turn_id
    agent_id: str             # 全局唯一 Agent ID
    session_id: str
    trace_id: str = ""        # 跨 Agent 全链路追踪 ID
    seq: int = 0
    phase: str = ""           # instruction/thinking/tool_call/tool_result/response/handoff/error/heartbeat
    role: str = ""            # user/assistant/system/tool
    handoff: HandoffInfo | None = None
    source_type: str = ""
    severity: str = "info"    # info / warn / error / critical
    token_count: int = 0
    duration_ms: int = 0
    time_start: int = 0       # epoch ms
    time_end: int | None = None
    blocks: list[ContentBlock] = field(default_factory=list)

    @classmethod
    def category_from_phase(cls, phase: str) -> str:
        """将底层 phase 映射到前端 5 分类。"""
        mapping = {
            "thinking": "思考",
            "tool_call": "工具",
            "tool_result": "工具",
            "handoff": "交互",
            "handoff_result": "交互",
            "response": "输出",
            "instruction": "输出",
            "error": "系统",
            "heartbeat": "系统",
            "source_status": "系统",
        }
        return mapping.get(phase, "系统")


class LogAdapter(ABC):
    """每个数据源实现此接口，将原生日志翻译为统一 Turn 流。"""

    @abstractmethod
    def agent_identity(self) -> AgentIdentity:
        """返回此适配器代表的 Agent 身份信息。"""
        ...

    @abstractmethod
    def parse_turns(self, since: int) -> list[Turn]:
        """从原生日志中解析出 since (epoch ms) 以来的 Turn 列表。

        每个来源的原生日志格式不同：
        - Claude Code: JSONL (type: user/assistant, content blocks)
        - OpenCode: SQLite DB (messages + tool_calls 表)
        - n8n: webhook JSON (execution nodes)
        - 自定义Agent: 结构化 JSONL / syslog

        但输出都是统一的 Turn 对象列表。
        """
        ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """检查此数据源的健康状态。"""
        ...
