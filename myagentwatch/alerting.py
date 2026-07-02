"""Alerting rule engine - evaluates config-driven rules against collected data."""

import json
import logging
import time
import urllib.request

from myagentwatch.db import database

logger = logging.getLogger("myagentwatch.alerting")


class AlertEngine:
    """Evaluates alert rules and manages alert lifecycle."""

    def __init__(self, config: dict):
        self.rules = config.get("alert_rules", [])
        self._alert_fired: dict[str, float] = {}  # rule_name -> last_fire_time

    def evaluate(self) -> list[dict]:
        """Evaluate all rules, return newly created alerts."""
        new_alerts = []
        for rule in self.rules:
            try:
                result = self._evaluate_rule(rule)
                if result:
                    new_alerts.append(result)
            except Exception as e:
                logger.error(f"Error evaluating rule '{rule.get('name')}': {e}")
        return new_alerts

    def _evaluate_rule(self, rule: dict) -> dict | None:
        name = rule.get("name", "unknown")
        metric = rule.get("metric", "")
        condition = rule.get("condition", ">")
        threshold = rule.get("threshold", 0)
        level = rule.get("level", "info")
        description = rule.get("description", name)

        with database() as conn:
            current_value = self._get_metric_value(conn, metric)

        if current_value is None:
            return None

        triggered = False
        if condition == ">":
            triggered = current_value > threshold
        elif condition == "<":
            triggered = current_value < threshold
        elif condition == ">=":
            triggered = current_value >= threshold
        elif condition == "<=":
            triggered = current_value <= threshold
        elif condition == "==":
            triggered = current_value == threshold

        if not triggered:
            return None

        # Check cooldown (don't fire same alert within 5 minutes)
        last = self._alert_fired.get(name, 0)
        now = time.time()
        if now - last < 300:
            return None

        self._alert_fired[name] = now

        # Check if there's already an active alert for this rule
        existing = self._has_active_alert(name)
        if existing:
            return None

        # Persist the alert
        alert_id = self._create_alert(rule, current_value, name, level, description)

        # Send webhook if configured
        webhook_url = rule.get("webhook_url", "")
        if webhook_url:
            self._send_webhook(webhook_url, name, level, description, current_value, threshold)

        return {
            "id": alert_id,
            "rule_name": name,
            "level": level,
            "message": f"{description}: current={current_value} threshold={threshold}",
            "metric": metric,
            "value": current_value,
        }

    def _send_webhook(self, url, name, level, description, value, threshold):
        """POST alert payload to configured webhook URL (generic JSON format)."""
        try:
            payload = json.dumps({
                "alert": name,
                "level": level,
                "description": description,
                "value": value,
                "threshold": threshold,
                "source": "MyAgentWatch",
                "timestamp": int(time.time()),
            }, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            logger.info(f"Webhook sent for alert '{name}' to {url}")
        except Exception as e:
            logger.error(f"Webhook failed for alert '{name}': {e}")

    def _get_metric_value(self, conn, metric: str):
        now = int(time.time() * 1000)
        one_hour_ago = now - 3600000

        if metric == "last_seen_delta":
            row = conn.execute(
                "SELECT MAX(? - last_seen_time) as max_delta FROM agents WHERE status = 'active'",
                (now,),
            ).fetchone()
            if row and row["max_delta"] is not None:
                return row["max_delta"] / 1000
            return 0

        elif metric == "session_cost":
            row = conn.execute(
                "SELECT MAX(total_cost) as max_cost FROM sessions WHERE status = 'active'"
            ).fetchone()
            return row["max_cost"] if row and row["max_cost"] else 0

        elif metric == "tool_failure_pct":
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM tool_calls WHERE timestamp >= ?",
                (one_hour_ago,),
            ).fetchone()["cnt"]
            if total == 0:
                return 0
            failed = conn.execute(
                "SELECT COUNT(*) as cnt FROM tool_calls "
                "WHERE status IN ('error', 'failed') AND timestamp >= ?",
                (one_hour_ago,),
            ).fetchone()["cnt"]
            return (failed / total) * 100

        elif metric == "cache_hit_pct":
            row = conn.execute(
                "SELECT COALESCE(SUM(cache_read), 0) as cache_read, "
                "COALESCE(SUM(cache_write), 0) as cache_write "
                "FROM token_records"
            ).fetchone()
            total = (row["cache_read"] or 0) + (row["cache_write"] or 0)
            return (row["cache_read"] / total) * 100 if total else 100

        elif metric == "cpu_pct":
            import psutil
            return psutil.cpu_percent(interval=0.2)

        elif metric == "memory_pct":
            import psutil
            return psutil.virtual_memory().percent

        elif metric == "disk_pct":
            import psutil
            return psutil.disk_usage("/").percent

        elif metric == "heartbeat_lost":
            timeout_sec = 300
            cutoff = now - timeout_sec * 1000
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM agents "
                "WHERE status = 'offline' AND last_heartbeat_at > 0 "
                "AND last_heartbeat_at < ?",
                (cutoff,),
            ).fetchone()
            return row["cnt"] if row else 0

        return None

    def _has_active_alert(self, name) -> bool:
        with database() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM alerts WHERE rule_name = ? AND is_active = 1",
                (name,),
            ).fetchone()
            return row["cnt"] > 0 if row else False

    def _create_alert(self, rule, current_value, name, level, description) -> int:
        with database() as conn:
            now = int(time.time() * 1000)
            cursor = conn.execute(
                "INSERT INTO alerts (rule_name, agent_id, level, message, is_active, created_at) "
                "VALUES (?, '', ?, ?, 1, ?)",
                (
                    name,
                    level,
                    f"{description}: value={current_value} threshold={rule.get('threshold')}",
                    now,
                ),
            )
            conn.commit()
            alert_id = cursor.lastrowid
            logger.warning(f"ALERT [{level}] {name}: {description}")
            try:
                from routes.api import _create_inbox_item
                _create_inbox_item(
                    recipient_id="天宇", item_type="alert",
                    severity=level if level in ("warn", "error", "critical") else "info",
                    title=f"告警: {description}",
                    body=f"当前值: {current_value}  阈值: {threshold}",
                    source_agent="system",
                )
            except Exception:
                pass
            return alert_id
