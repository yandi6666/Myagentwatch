"""Test that all source adapters are registered in SOURCE_REGISTRY (B1 regression)."""

from myagentwatch.sources import SOURCE_REGISTRY


def test_all_adapters_registered():
    """All built-in adapters must be in the registry."""
    expected = {
        "opencode_db",
        "opencode_log",
        "system",
        "sqlite_agent",
        "log_file",
    }
    registered = set(SOURCE_REGISTRY.keys())
    missing = expected - registered
    assert not missing, f"Missing from registry: {missing}"


def test_sqlite_agent_registered():
    """sqlite_agent adapter must be importable and registered."""
    assert "sqlite_agent" in SOURCE_REGISTRY
    from myagentwatch.sources.sqlite_agent import SQLiteAgentSource
    assert SOURCE_REGISTRY["sqlite_agent"] is SQLiteAgentSource


def test_log_file_registered():
    """log_file adapter must be importable and registered."""
    assert "log_file" in SOURCE_REGISTRY
    from myagentwatch.sources.log_file import LogFileSource
    assert SOURCE_REGISTRY["log_file"] is LogFileSource
