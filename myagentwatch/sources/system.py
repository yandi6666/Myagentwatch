"""System resource data source using psutil."""

import os
import time
from typing import Any

import psutil

from . import register_source
from .base import AgentInfo, CollectedData, SourceInterface


@register_source("system")
class SystemSource(SourceInterface):
    """Collects system resource metrics (CPU, memory, disk)."""

    def __init__(self, name: str = "system"):
        self.name = name

    def connect(self) -> bool:
        return True

    def discover_agents(self) -> list[AgentInfo]:
        return []

    def collect(self, since_timestamp: int) -> CollectedData:
        data = CollectedData(last_sync_time=int(time.time() * 1000))
        return data

    def health_check(self) -> dict[str, Any]:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        return {
            "name": self.name,
            "type": "system",
            "accessible": True,
            "cpu_pct": cpu,
            "memory_pct": mem.percent,
            "memory_used_mb": round(mem.used / (1024 * 1024), 1),
            "memory_total_mb": round(mem.total / (1024 * 1024), 1),
            "disk_pct": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "uptime_seconds": round(time.time() - psutil.boot_time(), 1),
        }
