"""Tests for collector module."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from myagentwatch.collector import Collector


def test_collector_creates_with_default_config():
    config = {"data_sources": []}
    c = Collector(config)
    assert "system" in c.sources


def test_collector_skips_disabled_sources():
    config = {
        "data_sources": [
            {
                "name": "disabled-db",
                "type": "opencode_db",
                "db_path": "/nonexistent",
                "enabled": False,
            },
        ]
    }
    c = Collector(config)
    assert "disabled-db" not in c.sources


def test_collector_health_returns_list():
    config = {"data_sources": []}
    c = Collector(config)
    health = c.get_health()
    assert isinstance(health, list)
    assert any(h["name"] == "system" for h in health)


def test_collector_active_agent_count():
    from myagentwatch.db import init_db
    init_db()
    config = {"data_sources": []}
    c = Collector(config)
    count = c.get_active_agent_count()
    assert count >= 0
