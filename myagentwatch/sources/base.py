"""Abstract base class for data sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentInfo:
    name: str
    agent_type: str
    model_id: str
    provider_id: str
    last_seen_time: int = 0
    display_name: str = ""
    group_name: str = ""


@dataclass
class SessionInfo:
    id: str
    title: str
    slug: str
    directory: str
    parent_id: str | None
    time_created: int
    time_updated: int
    summary_additions: int = 0
    summary_deletions: int = 0


@dataclass
class MessageInfo:
    id: str
    session_id: str
    role: str
    agent: str
    mode: str
    model_id: str
    provider_id: str
    finish: str | None
    cost: float
    tokens_input: int
    tokens_output: int
    tokens_reasoning: int
    cache_read: int
    cache_write: int
    time_created: int
    time_completed: int | None
    parent_id: str | None


@dataclass
class PartInfo:
    id: str
    message_id: str
    session_id: str
    part_type: str
    tool_name: str | None
    call_id: str | None
    tool_status: str | None
    tool_description: str | None
    tool_exit_code: int | None
    tool_duration_ms: int | None
    text_content: str | None
    step_type: str | None
    step_reason: str | None
    tokens_input: int
    tokens_output: int
    tokens_reasoning: int
    cache_read: int
    cache_write: int
    cost: float
    time_created: int


@dataclass
class CollectedData:
    agents: list[AgentInfo] = field(default_factory=list)
    sessions: list[SessionInfo] = field(default_factory=list)
    messages: list[MessageInfo] = field(default_factory=list)
    parts: list[PartInfo] = field(default_factory=list)
    last_sync_time: int = 0


class SourceInterface(ABC):
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the data source. Returns True on success."""
        ...

    @abstractmethod
    def discover_agents(self) -> list[AgentInfo]:
        """Discover agents from this data source."""
        ...

    @abstractmethod
    def collect(self, since_timestamp: int) -> CollectedData:
        """Collect incremental data since the given timestamp."""
        ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Check this data source's health."""
        ...
