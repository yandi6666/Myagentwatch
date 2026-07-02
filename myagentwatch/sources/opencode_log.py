"""OpenCode log file data source."""

import logging
import os
import re
import time
from typing import Any

from . import register_source
from .base import AgentInfo, CollectedData, SourceInterface

logger = logging.getLogger("myagentwatch.source.opencode_log")

# Log line pattern: LEVEL  TIMESTAMP +ELAPSED service=SERVICE ... message
LOG_PATTERN = re.compile(
    r"^(\w+)\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s\+(\d+)ms\s"
    r"(?:service=(\S+)\s)?(.*)$"
)


@register_source("opencode_log")
class OpenCodeLogSource(SourceInterface):
    """Parses OpenCode runtime log files for supplementary data."""

    def __init__(self, name: str, log_dir: str):
        self.name = name
        self.log_dir = log_dir
        self._file_positions: dict[str, int] = {}  # filename -> byte offset

    def connect(self) -> bool:
        return os.path.isdir(self.log_dir)

    def discover_agents(self) -> list[AgentInfo]:
        return []

    def collect(self, since_timestamp: int) -> CollectedData:
        data = CollectedData(last_sync_time=since_timestamp)

        try:
            log_files = sorted(
                [f for f in os.listdir(self.log_dir) if f.endswith(".log")]
            )
            if not log_files:
                return data

            # Read only the latest log file (most recent)
            latest = log_files[-1]
            filepath = os.path.join(self.log_dir, latest)
            offset = self._file_positions.get(latest, 0)

            with open(filepath, encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                new_lines = f.readlines()
                self._file_positions[latest] = f.tell()

            parsed = []
            for line in new_lines:
                m = LOG_PATTERN.match(line.strip())
                if m:
                    parsed.append(
                        {
                            "level": m.group(1),
                            "timestamp": m.group(2),
                            "elapsed_ms": m.group(3),
                            "service": m.group(4) or "",
                            "message": m.group(5) or "",
                        }
                    )

            # Log collected lines as activity (only significant ones)
            for entry in parsed:
                if entry["level"] in ("WARN", "ERROR"):
                    logger.info(
                        f"Log [{entry['level']}] {entry['service']}: {entry['message'][:80]}"
                    )

            data.last_sync_time = int(time.time() * 1000)
        except Exception as e:
            logger.error(f"Error reading logs from {self.name}: {e}")

        return data

    def health_check(self) -> dict[str, Any]:
        ok = os.path.isdir(self.log_dir)
        info = {"name": self.name, "type": "opencode_log", "accessible": ok}
        if ok:
            try:
                files = [f for f in os.listdir(self.log_dir) if f.endswith(".log")]
                info["log_file_count"] = len(files)
                if files:
                    latest = files[-1]
                    info["latest_log"] = latest
                    size = os.path.getsize(os.path.join(self.log_dir, latest))
                    info["latest_size_kb"] = round(size / 1024, 1)
            except Exception:
                pass
        return info

    def get_recent_lines(self, count: int = 50, level: str = None) -> list[dict]:
        """Return recent log lines for the live stream."""
        try:
            log_files = sorted(
                [f for f in os.listdir(self.log_dir) if f.endswith(".log")]
            )
            if not log_files:
                return []

            latest = os.path.join(self.log_dir, log_files[-1])
            with open(latest, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            result = []
            for line in reversed(lines[-500:]):
                m = LOG_PATTERN.match(line.strip())
                if m:
                    lvl = m.group(1)
                    if level and lvl != level:
                        continue
                    result.append(
                        {
                            "level": lvl,
                            "timestamp": m.group(2),
                            "elapsed_ms": m.group(3),
                            "service": m.group(4) or "",
                            "message": m.group(5) or "",
                        }
                    )
                if len(result) >= count:
                    break

            return list(reversed(result))
        except Exception as e:
            logger.error(f"Error getting log lines: {e}")
            return []
