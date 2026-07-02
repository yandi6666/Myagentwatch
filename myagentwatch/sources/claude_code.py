"""Claude Code JSONL data source adapter.

Reads Claude Code conversation logs from ~/.claude/ and extracts:
- Agent discovery (Claude Code main + sub-agents)
- Token usage (input/output/cache from message.usage)
- Tool calls (tool_use blocks)
- Session metadata
"""

import json
import logging
import os
import time
from typing import Any

from . import register_source
from .base import (
    AgentInfo,
    CollectedData,
    MessageInfo,
    PartInfo,
    SessionInfo,
    SourceInterface,
)
from .log_adapter import (
    AgentIdentity,
    ContentBlock,
    HandoffInfo,
    LogAdapter,
    Turn,
)

logger = logging.getLogger("myagentwatch.source.claude_code")

CLAUDE_DIR = os.path.expanduser("~/.claude")


def _find_project_dirs():
    """Yield (project_name, project_path) for each Claude Code project."""
    projects_dir = os.path.join(CLAUDE_DIR, "projects")
    if not os.path.isdir(projects_dir):
        return
    for name in os.listdir(projects_dir):
        path = os.path.join(projects_dir, name)
        if os.path.isdir(path):
            yield name, path


def _find_session_files(project_path: str):
    """Yield (session_id, jsonl_path) for each session in a project."""
    for entry in os.listdir(project_path):
        if entry.endswith(".jsonl") and not entry.startswith("."):
            session_id = entry[:-6]  # remove .jsonl
            yield session_id, os.path.join(project_path, entry)


def _find_subagent_files(project_path: str, session_id: str):
    """Yield (agent_type, jsonl_path) for each sub-agent session."""
    sub_dir = os.path.join(project_path, session_id, "subagents")
    if not os.path.isdir(sub_dir):
        return
    for entry in os.listdir(sub_dir):
        if entry.endswith(".jsonl"):
            # Try to get agent type from .meta.json
            meta_path = os.path.join(sub_dir, entry.replace(".jsonl", ".meta.json"))
            agent_type = "subagent"
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                    agent_type = meta.get("agentType", "subagent")
                except Exception:
                    pass
            yield agent_type, os.path.join(sub_dir, entry)


def _parse_timestamp(ts_str: str) -> int:
    """Parse ISO timestamp string to epoch milliseconds."""
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000)


def _file_mtime_ms(path: str) -> int:
    """Return file mtime in epoch milliseconds, or now if unavailable."""
    try:
        return int(os.path.getmtime(path) * 1000)
    except OSError:
        return int(time.time() * 1000)


@register_source("claude_code")
class ClaudeCodeSource(SourceInterface, LogAdapter):
    """Reads Claude Code JSONL conversation logs."""

    def __init__(self, name: str, **kwargs):
        self.name = name
        self.claude_dir = os.path.expanduser(kwargs.get("claude_dir", CLAUDE_DIR))
        self._file_positions: dict[str, int] = {}  # filepath -> byte offset (用于 collect)
        self._turn_file_positions: dict[str, int] = {}  # filepath -> byte offset (用于 parse_turns，独立于 collect)
        self._session_agents: dict[str, str] = {}  # session_id -> agent_name
        self._agent_cache: list[AgentInfo] | None = None
        self._agent_cache_mtime: float = 0

    def connect(self) -> bool:
        projects_dir = os.path.join(self.claude_dir, "projects")
        return os.path.isdir(projects_dir)

    def discover_agents(self) -> list[AgentInfo]:
        # Check cache: only rescan if projects dir mtime changed
        projects_dir = os.path.join(self.claude_dir, "projects")
        try:
            latest_mtime = os.path.getmtime(projects_dir)
        except OSError:
            latest_mtime = 0
        if self._agent_cache is not None and latest_mtime <= self._agent_cache_mtime:
            return self._agent_cache

        agents: dict[str, AgentInfo] = {}

        for proj_name, proj_path in _find_project_dirs():
            for session_id, jsonl_path in _find_session_files(proj_path):
                try:
                    with open(jsonl_path, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                entry = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if entry.get("type") != "assistant":
                                continue
                            msg = entry.get("message", {})
                            model = msg.get("model", "")
                            if not model:
                                continue

                            key = f"claude_code:{model}"
                            seen_at = _file_mtime_ms(jsonl_path)
                            if key not in agents:
                                agents[key] = AgentInfo(
                                    name="Claude Code",
                                    agent_type="claude_code",
                                    model_id=model,
                                    provider_id=model.split("-")[0] if "-" in model else model,
                                    last_seen_time=seen_at,
                                    display_name=f"Claude Code ({model})",
                                    group_name="Claude Code",
                                )
                            else:
                                agents[key].last_seen_time = max(agents[key].last_seen_time, seen_at)

                            # Sub-agents
                            for agent_type, sub_path in _find_subagent_files(
                                proj_path, session_id
                            ):
                                sub_key = f"claude_code_sub:{agent_type}"
                                sub_agent_name = f"Claude Code {agent_type}"
                                sub_seen_at = _file_mtime_ms(sub_path)
                                if sub_key not in agents:
                                    agents[sub_key] = AgentInfo(
                                        name=sub_agent_name,
                                        agent_type=agent_type,
                                        model_id=model,
                                        provider_id=model.split("-")[0] if "-" in model else model,
                                        last_seen_time=sub_seen_at,
                                        display_name=f"Claude Code {agent_type}",
                                        group_name="Claude Code",
                                    )
                                else:
                                    agents[sub_key].last_seen_time = max(
                                        agents[sub_key].last_seen_time, sub_seen_at
                                    )

                            break  # Only need one assistant message per session for discovery
                except Exception as e:
                    logger.error(f"Error discovering agents from {jsonl_path}: {e}")

        logger.info(f"Discovered {len(agents)} Claude Code agents")
        self._agent_cache = list(agents.values())
        self._agent_cache_mtime = latest_mtime
        return self._agent_cache

    def collect(self, since_timestamp: int) -> CollectedData:
        data = CollectedData(last_sync_time=since_timestamp)

        # Populate agents from discovery
        data.agents = self.discover_agents()

        try:
            for proj_name, proj_path in _find_project_dirs():
                for session_id, jsonl_path in _find_session_files(proj_path):
                    subagent_files = dict(
                        _find_subagent_files(proj_path, session_id)
                    )

                    offset = self._file_positions.get(jsonl_path, 0)
                    file_size = os.path.getsize(jsonl_path)
                    if offset >= file_size:
                        continue

                    with open(jsonl_path, encoding="utf-8", errors="replace") as f:
                        f.seek(offset)
                        lines = f.readlines()
                        self._file_positions[jsonl_path] = f.tell()

                    self._parse_session_lines(
                        data, lines, session_id, proj_name, offset
                    )

                    # Parse sub-agent files
                    for agent_type, sub_path in subagent_files.items():
                        sub_offset = self._file_positions.get(sub_path, 0)
                        sub_size = os.path.getsize(sub_path)
                        if sub_offset >= sub_size:
                            continue
                        with open(sub_path, encoding="utf-8", errors="replace") as f:
                            f.seek(sub_offset)
                            sub_lines = f.readlines()
                            self._file_positions[sub_path] = f.tell()
                        self._parse_session_lines(
                            data, sub_lines, session_id + "_sub",
                            proj_name, sub_offset, agent_type=agent_type,
                        )

            data.last_sync_time = int(time.time() * 1000)
            logger.info(
                f"Collected from Claude Code: {len(data.sessions)} sessions, "
                f"{len(data.messages)} msgs, {len(data.parts)} parts"
            )
        except Exception as e:
            logger.error(f"Error collecting from Claude Code: {e}")

        return data

    def _parse_session_lines(
        self,
        data: CollectedData,
        lines: list[str],
        session_id: str,
        project_name: str,
        base_offset: int,
        agent_type: str = "claude_code",
    ):
        """Parse JSONL lines and populate CollectedData."""
        current_model = ""
        msg_idx = 0

        # Discover model and session title
        session_title = ""
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") == "assistant":
                current_model = entry.get("message", {}).get("model", current_model)
            elif entry.get("type") == "user" and not session_title:
                role = entry.get("message", {}).get("role", "")
                if role == "user":
                    content = entry.get("message", {}).get("content", "")
                    if isinstance(content, str):
                        session_title = content[:80]
                    elif isinstance(content, list) and content:
                        first = content[0]
                        if isinstance(first, dict) and first.get("type") == "text":
                            session_title = first.get("text", "")[:80]

        if not current_model:
            return

        agent_name = f"Claude Code {agent_type}" if agent_type != "claude_code" else "Claude Code"
        msg_count_before = len(data.messages)

        seen_models: set[str] = set()

        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = entry.get("type", "")
            ts = _parse_timestamp(entry.get("timestamp", ""))
            msg_id = entry.get("message", {}).get("id", f"{session_id}:{msg_idx}")

            if etype == "assistant":
                msg = entry.get("message", {})
                msg_model = msg.get("model", "")
                if msg_model and msg_model not in seen_models:
                    seen_models.add(msg_model)
                    from .base import AgentInfo

                    data.agents.append(
                        AgentInfo(
                            name=agent_name,
                            agent_type=agent_type,
                            model_id=msg_model,
                            provider_id=msg_model.split("-")[0] if "-" in msg_model else msg_model,
                            last_seen_time=ts,
                            display_name=f"{agent_name} ({msg_model})",
                            group_name="Claude Code",
                        )
                    )
                usage = msg.get("usage", {})
                from myagentwatch.pricing import calculate_cost
                cost = calculate_cost(
                    msg.get("model", ""),
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                    cache_read=usage.get("cache_read_input_tokens", 0),
                    cache_write=usage.get("cache_creation_input_tokens", 0),
                )

                data.messages.append(
                    MessageInfo(
                        id=msg_id,
                        session_id=session_id,
                        role="assistant",
                        agent=agent_name,
                        mode=msg.get("model", ""),
                        model_id=msg.get("model", ""),
                        provider_id=msg.get("model", "").split("-")[0] if "-" in msg.get("model", "") else "",
                        finish=msg.get("stop_reason"),
                        cost=cost,
                        tokens_input=usage.get("input_tokens", 0),
                        tokens_output=usage.get("output_tokens", 0),
                        tokens_reasoning=0,
                        cache_read=usage.get("cache_read_input_tokens", 0),
                        cache_write=usage.get("cache_creation_input_tokens", 0),
                        time_created=ts,
                        time_completed=ts,
                        parent_id=None,
                    )
                )

                # Extract tool_use blocks as parts
                for block in msg.get("content", []):
                    if block.get("type") == "tool_use":
                        data.parts.append(
                            PartInfo(
                                id=block.get("id", f"{msg_id}:{block.get('name', '')}"),
                                message_id=msg_id,
                                session_id=session_id,
                                part_type="tool",
                                tool_name=block.get("name", ""),
                                call_id=block.get("id", ""),
                                tool_status="completed",
                                tool_description=str(block.get("input", {}))[:500],
                                tool_exit_code=0,
                                tool_duration_ms=0,
                                text_content=None,
                                step_type=None,
                                step_reason=None,
                                tokens_input=0,
                                tokens_output=0,
                                tokens_reasoning=0,
                                cache_read=0,
                                cache_write=0,
                                cost=0,
                                time_created=ts,
                            )
                        )
                    elif block.get("type") == "thinking":
                        data.parts.append(
                            PartInfo(
                                id=f"{msg_id}:thinking",
                                message_id=msg_id,
                                session_id=session_id,
                                part_type="thinking",
                                tool_name=None,
                                call_id=None,
                                tool_status=None,
                                tool_description=None,
                                tool_exit_code=None,
                                tool_duration_ms=None,
                                text_content=block.get("thinking", "")[:500],
                                step_type=None,
                                step_reason=None,
                                tokens_input=0,
                                tokens_output=0,
                                tokens_reasoning=0,
                                cache_read=0,
                                cache_write=0,
                                cost=0,
                                time_created=ts,
                            )
                        )
                    elif block.get("type") == "text" and block.get("text"):
                        data.parts.append(
                            PartInfo(
                                id=f"{msg_id}:text",
                                message_id=msg_id,
                                session_id=session_id,
                                part_type="text",
                                tool_name=None,
                                call_id=None,
                                tool_status=None,
                                tool_description=None,
                                tool_exit_code=None,
                                tool_duration_ms=None,
                                text_content=block.get("text", "")[:500],
                                step_type=None,
                                step_reason=None,
                                tokens_input=0,
                                tokens_output=0,
                                tokens_reasoning=0,
                                cache_read=0,
                                cache_write=0,
                                cost=0,
                                time_created=ts,
                            )
                        )

                msg_idx += 1

        # Only create session if we actually added messages
        if len(data.messages) > msg_count_before:
            data.sessions.append(
                SessionInfo(
                    id=session_id,
                    title=session_title or f"Claude Code {agent_type}",
                    slug="",
                    directory=project_name,
                    parent_id=None,
                    time_created=_parse_timestamp(
                        json.loads(lines[0]).get("timestamp", "")
                    ) if lines else int(time.time() * 1000),
                    time_updated=int(time.time() * 1000),
                )
            )

    def agent_identity(self) -> AgentIdentity:
        import hashlib

        return AgentIdentity(
            source_type="claude_code",
            source_name=self.name,
            project_hash=hashlib.md5(self.claude_dir.encode()).hexdigest()[:7],
            agent_role="main",
            agent_name="Claude Code",
            model_id="",  # 在 parse_turns 中按模型细分
        )

    def parse_turns(self, since: int) -> list[Turn]:
        """从 JSONL 解析 Turn 流 — LogAdapter 接口实现。

        使用独立的 _turn_file_positions，与 collect() 的文件位置互不干扰。
        返回全局唯一的 Turn 对象，包含完整内容和 severity 标记。
        """
        turns: list[Turn] = []
        identity = self.agent_identity()

        try:
            for proj_name, proj_path in _find_project_dirs():
                for session_id, jsonl_path in _find_session_files(proj_path):
                    file_size = os.path.getsize(jsonl_path)
                    if file_size == 0:
                        continue

                    offset = self._turn_file_positions.get(jsonl_path, 0)
                    if offset >= file_size:
                        continue

                    with open(jsonl_path, encoding="utf-8", errors="replace") as f:
                        f.seek(offset)
                        lines = f.readlines()
                        self._turn_file_positions[jsonl_path] = f.tell()

                    session_turns = self._lines_to_turns(
                        lines, session_id, proj_name, identity, since=since
                    )
                    turns.extend(session_turns)

                    # 子 Agent 文件
                    subagent_files = dict(
                        _find_subagent_files(proj_path, session_id)
                    )
                    for agent_type, sub_path in subagent_files.items():
                        sub_size = os.path.getsize(sub_path)
                        sub_offset = self._turn_file_positions.get(sub_path, 0)
                        if sub_offset >= sub_size:
                            continue
                        with open(sub_path, encoding="utf-8", errors="replace") as f:
                            f.seek(sub_offset)
                            sub_lines = f.readlines()
                            self._turn_file_positions[sub_path] = f.tell()

                        sub_identity = AgentIdentity(
                            source_type="claude_code",
                            source_name=self.name,
                            project_hash=identity.project_hash,
                            agent_role="subagent",
                            agent_name=f"Claude Code {agent_type}",
                            model_id="",
                        )
                        sub_turns = self._lines_to_turns(
                            sub_lines, f"{session_id}_sub", proj_name,
                            sub_identity, parent_session_id=session_id,
                            agent_type=agent_type, since=since,
                        )
                        turns.extend(sub_turns)

        except Exception as e:
            logger.error(f"Error parsing turns from Claude Code: {e}")

        return turns

    def _lines_to_turns(
        self,
        lines: list[str],
        session_id: str,
        project_name: str,
        identity: AgentIdentity,
        parent_session_id: str | None = None,
        agent_type: str = "claude_code",
        since: int = 0,
    ) -> list[Turn]:
        """将 JSONL 行解析为 Turn 对象列表。"""
        import hashlib

        turns: list[Turn] = []
        current_model = ""
        seq = 0
        current_trace_id = ""
        agent_name = identity.agent_name

        # 第一遍：发现模型
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "assistant":
                current_model = entry.get("message", {}).get("model", "")
                if current_model:
                    break

        if not current_model:
            return turns

        # 生成完整 agent_id
        proj_hash = hashlib.md5(project_name.encode()).hexdigest()[:7]
        full_agent_id = (
            f"{identity.source_type}::{identity.source_name}::"
            f"{proj_hash}::{identity.agent_role}::"
            f"{identity.agent_name}::{current_model}"
        )

        # 第二遍：逐个 entry → Turn
        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = entry.get("type", "")
            ts = _parse_timestamp(entry.get("timestamp", ""))
            if ts < since:
                continue

            msg = entry.get("message", {})
            msg_id = msg.get("id", f"{session_id}:{seq}")

            seq += 1
            blocks: list[ContentBlock] = []
            phase = ""
            role = ""
            severity = "info"
            tokens = 0
            duration_ms = 0
            handoff: HandoffInfo | None = None

            if etype == "user":
                msg_role = msg.get("role", "user")
                content = msg.get("content", "")

                # tool_result: user 消息中包含 tool_result 内容块
                if isinstance(content, list):
                    has_tool_result = any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    )
                    if has_tool_result:
                        role = "tool"
                        phase = "tool_result"
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                result_text = block.get("content", "")
                                is_error = block.get("is_error", False)
                                blocks.append(ContentBlock(
                                    block_type="tool_output",
                                    content=str(result_text)[:5000] if result_text else "",
                                    tool_call_id=block.get("tool_use_id", ""),
                                    char_count=len(str(result_text)) if result_text else 0,
                                ))
                                if is_error:
                                    severity = "error"
                    else:
                        # 普通 user 消息
                        phase = "instruction"
                        role = "user"
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                        content = "\n".join(text_parts)
                        if content:
                            blocks.append(ContentBlock(
                                block_type="user_text",
                                content=str(content)[:2000],
                                char_count=len(str(content)),
                            ))
                        current_trace_id = f"trace_{session_id}_{int(ts / 1000)}"
                elif isinstance(content, str) and content:
                    phase = "instruction"
                    role = "user"
                    blocks.append(ContentBlock(
                        block_type="user_text",
                        content=content[:2000],
                        char_count=len(content),
                    ))
                    current_trace_id = f"trace_{session_id}_{int(ts / 1000)}"

            elif etype == "assistant":
                role = "assistant"
                content_blocks = msg.get("content", [])
                thinking_texts = []
                tool_count = 0

                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "thinking":
                        thinking_text = block.get("thinking", "")
                        if thinking_text:
                            thinking_texts.append(thinking_text)
                            blocks.append(ContentBlock(
                                block_type="thinking",
                                content=thinking_text,
                                char_count=len(thinking_text),
                            ))

                    elif block.get("type") == "tool_use":
                        tool_count += 1
                        tool_name = block.get("name", "")
                        tool_id = block.get("id", "")
                        tool_input = block.get("input", {})
                        blocks.append(ContentBlock(
                            block_type="tool_input",
                            content=json.dumps(tool_input, ensure_ascii=False),
                            tool_name=tool_name,
                            tool_call_id=tool_id,
                            mime_type="application/json",
                            char_count=len(json.dumps(tool_input, ensure_ascii=False)),
                        ))

                    elif block.get("type") == "text":
                        text_content = block.get("text", "")
                        if text_content:
                            blocks.append(ContentBlock(
                                block_type="response_text",
                                content=text_content,
                                char_count=len(text_content),
                            ))

                # 根据内容块确定 phase
                if thinking_texts and not tool_count:
                    phase = "thinking"
                elif tool_count > 0:
                    phase = "tool_call"
                else:
                    phase = "response"

                usage = msg.get("usage", {})
                tokens = (
                    usage.get("input_tokens", 0)
                    + usage.get("output_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                )

                # 检查子 Agent 交接
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        if tool_name in ("Agent", "Task"):
                            tool_input = block.get("input", {})
                            subagent_type = tool_input.get("subagent_type", "")
                            if subagent_type:
                                handoff = HandoffInfo(
                                    from_agent_id=full_agent_id,
                                    to_agent_id="",
                                    to_session_id="",
                                    subagent_type=subagent_type,
                                    prompt=tool_input.get("prompt", "") or tool_input.get("description", ""),
                                    status="running",
                                )
                                phase = "handoff"
                                break

                # 错误检测
                stop_reason = msg.get("stop_reason", "")
                if stop_reason in ("error", "max_tokens"):
                    severity = "error"
                for block in content_blocks:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("thinking", "")
                        if isinstance(text, str) and any(
                            kw in text.lower()
                            for kw in ("error", "traceback", "exception", "failed")
                        ):
                            severity = "error"
                            break

            else:
                continue

            turn = Turn(
                turn_id=f"{full_agent_id}::{session_id}::{seq}",
                natural_key=f"{full_agent_id}::{session_id}::{seq}",
                agent_id=full_agent_id,
                session_id=session_id,
                trace_id=current_trace_id,
                seq=seq,
                phase=phase,
                role=role,
                handoff=handoff,
                source_type="claude_code",
                severity=severity,
                token_count=tokens if etype == "assistant" else 0,
                duration_ms=duration_ms,
                time_start=ts,
                time_end=ts,
                blocks=blocks,
            )
            turns.append(turn)

        return turns

    def health_check(self) -> dict[str, Any]:
        ok = os.path.isdir(os.path.join(self.claude_dir, "projects"))
        info = {"name": self.name, "type": "claude_code", "accessible": ok}
        if ok:
            try:
                session_count = 0
                for _, proj_path in _find_project_dirs():
                    for _, _ in _find_session_files(proj_path):
                        session_count += 1
                info["session_count"] = session_count
            except Exception:
                pass
        return info

    def get_recent_lines(self, count: int = 50, level: str = None) -> list[dict]:
        """Return recent conversation snippets for the live stream."""
        result = []
        for _, proj_path in _find_project_dirs():
            for session_id, jsonl_path in _find_session_files(proj_path):
                try:
                    with open(jsonl_path, encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    for line in reversed(lines[-500:]):
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        etype = entry.get("type", "")
                        ts = entry.get("timestamp", "")
                        if etype == "assistant":
                            msg = entry.get("message", {})
                            model = msg.get("model", "")
                            usage = msg.get("usage", {})
                            result.append({
                                "level": "INFO",
                                "timestamp": ts,
                                "service": f"Claude Code ({model})",
                                "message": (
                                    f"in:{usage.get('input_tokens', 0)} "
                                    f"out:{usage.get('output_tokens', 0)} "
                                    f"cache:{usage.get('cache_read_input_tokens', 0)}"
                                ),
                            })
                        elif etype == "user":
                            role = entry.get("message", {}).get("role", "")
                            text = ""
                            content = entry.get("message", {}).get("content", "")
                            if isinstance(content, str):
                                text = content[:100]
                            elif isinstance(content, list) and content:
                                first = content[0]
                                if isinstance(first, dict) and first.get("type") == "text":
                                    text = first.get("text", "")[:100]
                            if text:
                                result.append({
                                    "level": "INFO",
                                    "timestamp": ts,
                                    "service": "User",
                                    "message": text,
                                })
                        if len(result) >= count:
                            break
                except Exception:
                    pass
                if len(result) >= count:
                    break
            if len(result) >= count:
                break
        return list(reversed(result[:count]))
