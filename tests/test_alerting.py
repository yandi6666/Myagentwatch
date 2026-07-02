"""Test alert engine evaluation (B4 regression)."""

import contextlib
import tempfile

from myagentwatch.alerting import AlertEngine


def test_alert_engine_evaluate_no_rules():
    """Alert engine with no rules returns empty list."""
    engine = AlertEngine({"alert_rules": []})
    alerts = engine.evaluate()
    assert alerts == []


def test_alert_engine_metric_not_triggered():
    """Alert should not fire when value is under threshold."""
    import os

    import myagentwatch.db as db_module

    # Save globals
    saved_path = db_module.DB_PATH

    # Use temp DB so we don't touch the real one
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db_module.DB_PATH = tmp
        db_module.init_db()

        rules = [
            {
                "name": "test_idle",
                "description": "Test idle",
                "metric": "last_seen_delta",
                "condition": ">",
                "threshold": 999999,
                "level": "warn",
            }
        ]
        engine = AlertEngine({"alert_rules": rules})
        alerts = engine.evaluate()
        assert alerts == []
    finally:
        db_module.DB_PATH = saved_path
        with contextlib.suppress(OSError):
            os.unlink(tmp)
