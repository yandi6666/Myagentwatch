"""Generic log file data source adapter.

For any tool that writes agent activity as structured log files
(JSON Lines, CSV, or custom regex-captured formats).

Supports: Strix output, any CLI tool with structured stdout logs.
"""

import glob
import json
import logging
import os
import time
from typing import Any

from . import register_source
from .base import AgentInfo, CollectedData, PartInfo, SourceInterface

logger = logging.getLogger("myagentwatch.source.log_file")


@register_source("log_file")
class LogFileSource(SourceInterface):
    """Generic adapter for any tool that outputs structured log files.

    Config YAML keys:
        path:           file path or glob pattern (e.g. "~/.strix/tasks/*.jsonl")
        format:         "json_lines" (default), "csv"
        agent_field:    field name containing agent name (default: "agent")
        model_field:    field name containing model ID (default: "model")
        provider_field: field name containing provider (default: "provider")
        type_field:     field name for event type (default: "type")
        text_field:     field name for text content (default: "text")
        timestamp_field: field name for timestamp (default: "timestamp")
    """

    def __init__(self, name: str, path: str, **kwargs):
        self.name = name
        self.path_pattern = os.path.expanduser(path)
        self.format = kwargs.get("format", "json_lines")
        self.agent_field = kwargs.get("agent_field", "agent")
        self.model_field = kwargs.get("model_field", "model")
        self.provider_field = kwargs.get("provider_field", "provider")
        self.type_field = kwargs.get("type_field", "type")
        self.text_field = kwargs.get("text_field", "text")
        self.timestamp_field = kwargs.get("timestamp_field", "timestamp")
        self._file_positions: dict[str, int] = {}
        self._file_agents: dict[str, set] = {}

    def connect(self) -> bool:
        files = self._list_files()
        if not files:
            logger.warning(f"No log files found: {self.path_pattern}")
            return False
        logger.info(f"Log file source '{self.name}' found {len(files)} files")
        return True

    def _list_files(self) -> list[str]:
        return sorted(glob.glob(self.path_pattern))

    def discover_agents(self) -> list[AgentInfo]:
        agents_dict: dict[str, AgentInfo] = {}

        for filepath in self._list_files():
            try:
                with open(filepath, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        name = ""
                        model = ""
                        provider = ""
                        if self.format == "json_lines":
                            try:
                                obj = json.loads(line)
                                name = obj.get(self.agent_field, "")
                                model = obj.get(self.model_field, "")
                                provider = obj.get(self.provider_field, "")
                            except json.JSONDecodeError:
                                continue
                        elif self.format == "csv":
                            parts = line.split(",")
                            if parts:
                                name = parts[0] if self.agent_field == "agent" else ""

                        if name and name not in agents_dict:
                            agents_dict[name] = AgentInfo(
                                name=name,
                                agent_type=name,
                                model_id=model,
                                provider_id=provider,
                                last_seen_time=int(time.time() * 1000),
                            )
            except Exception as e:
                logger.error(f"Error reading {filepath}: {e}")

        agents = list(agents_dict.values())
        logger.info(f"Discovered {len(agents)} agents from {self.name}")
        return agents

    def collect(self, since_timestamp: int) -> CollectedData:
        data = CollectedData(last_sync_time=since_timestamp)
        now = int(time.time() * 1000)

        for filepath in self._list_files():
            try:
                offset = self._file_positions.get(filepath, 0)
                with open(filepath, encoding="utf-8", errors="replace") as f:
                    f.seek(offset)
                    new_lines = f.readlines()
                    self._file_positions[filepath] = f.tell()

                for i, line in enumerate(new_lines):
                    line = line.strip()
                    if not line:
                        continue

                    ts = since_timestamp + i  # sequential ordering
                    if self.format == "json_lines":
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        text = obj.get(self.text_field, "")

                        part_id = f"{filepath}:{offset + i}"
                        data.parts.append(
                            PartInfo(
                                id=part_id,
                                message_id="",
                                session_id=obj.get("session_id", ""),
                                part_type="text" if text else "tool",
                                tool_name=obj.get("tool", None),
                                call_id=obj.get("call_id", None),
                                tool_status=obj.get("status", None),
                                text_content=text[:1000] if text else None,
                                tokens_input=obj.get("tokens_input", 0) or 0,
                                tokens_output=obj.get("tokens_output", 0) or 0,
                                tokens_reasoning=obj.get("tokens_reasoning", 0) or 0,
                                cost=obj.get("cost", 0) or 0,
                                time_created=ts,
                            )
                        )
            except Exception as e:
                logger.error(f"Error collecting from {filepath}: {e}")

        data.last_sync_time = now
        return data

    def health_check(self) -> dict[str, Any]:
        files = self._list_files()
        accessible = len(files) > 0
        info = {
            "name": self.name,
            "type": "log_file",
            "accessible": accessible,
            "file_count": len(files),
        }
        if files:
            info["latest_file"] = os.path.basename(files[-1])
        return info

    def get_recent_lines(self, count: int = 50, level: str = None) -> list[dict]:
        """Return recent log lines for the live stream widget."""
        result = []
        for filepath in reversed(self._list_files()):
            try:
                with open(filepath, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for line in reversed(lines[-200:]):
                    line = line.strip()
                    if not line:
                        continue
                    if self.format == "json_lines":
                        try:
                            obj = json.loads(line)
                            result.append(
                                {
                                    "level": obj.get("level", "INFO"),
                                    "timestamp": obj.get(self.timestamp_field, ""),
                                    "service": obj.get("service", self.name),
                                    "message": obj.get(self.text_field, line[:200]),
                                }
                            )
                        except json.JSONDecodeError:
                            result.append(
                                {
                                    "level": "INFO",
                                    "timestamp": "",
                                    "service": self.name,
                                    "message": line[:200],
                                }
                            )
                    if len(result) >= count:
                        break
                if len(result) >= count:
                    break
            except Exception as e:
                logger.error(f"Error reading {filepath}: {e}")

        return list(reversed(result[:count]))
