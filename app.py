"""MyAgentWatch — AI Agent Team Monitoring Tool.
Flask + Flask-SocketIO + D3 Force Topology.
"""

import atexit
import logging
import os
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO

sys.path.insert(0, os.path.dirname(__file__))

from myagentwatch.alerting import AlertEngine
from myagentwatch.collector import Collector
from myagentwatch.config import load_config
from myagentwatch.db import database, init_db
from routes.api import register_api_routes
from routes.api import flush_heartbeats
from routes.ws import build_agent_delta, build_snapshot

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("myagentwatch")


# ---------- Secret Key ----------
def _load_secret_key() -> str:
    key_file = os.path.join(os.path.dirname(__file__), "data", ".secret_key")
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read().decode()
    key = os.urandom(32).hex()
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    with open(key_file, "w") as f:
        f.write(key)
    return key


# ---------- Flask ----------
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["SECRET_KEY"] = _load_secret_key()
CORS(app)

# ---------- SocketIO ----------
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ---------- Config ----------
config = load_config()
PORT = int(os.environ.get("MYAGENTWATCH_PORT", 10000))
POLL_INTERVAL = config.get("poll_interval", 2)

# ---------- Database ----------
init_db()
logger.info("MyAgentWatch database initialized")

# ---------- Collector + Alerting ----------
collector = Collector(config)
alert_engine = AlertEngine(config)

# ---------- Routes + WS Events ----------
register_api_routes(app, collector, config, socketio)
from routes.agent_tasks_api import register_agent_task_routes
register_agent_task_routes(app, socketio)
from routes.chat_api import register_chat_routes
register_chat_routes(app, socketio)


# ---------- Error Handlers ----------
@app.errorhandler(500)
def handle_500(e):
    logger.error(f"Internal error: {e}")
    return jsonify({"error": "internal_error", "message": str(e)}), 500


@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "not_found"}), 404


# ---------- Scheduler ----------
scheduler = BackgroundScheduler()
START_TIME = time.time()
app.config["START_TIME"] = START_TIME


# ── Push tracking ──
_last_full_broadcast = 0
_agent_id_cache: list[str] = []
FULL_BROADCAST_INTERVAL = 10  # seconds between full-snapshot pushes


def _collect_and_push():
    global _last_full_broadcast, _agent_id_cache
    try:
        flush_heartbeats()
        collector.collect_all()

        now = time.time()
        # Full snapshot at reduced frequency (also refreshes agent cache)
        if now - _last_full_broadcast >= FULL_BROADCAST_INTERVAL:
            _last_full_broadcast = now
            snapshot = build_snapshot()
            if snapshot:
                socketio.emit("stat_snapshot", snapshot)
                _agent_id_cache = [a["id"] for a in snapshot.get("agents", [])]
        else:
            # Scoped deltas to subscribed clients (2s cadence)
            for aid in _agent_id_cache:
                delta = build_agent_delta(aid)
                if delta:
                    socketio.emit("agent_delta", delta, room=f"agent:{aid}")

        for alert in alert_engine.evaluate():
            socketio.emit("alert_event", alert)
    except Exception as e:
        logger.error(f"Collection cycle failed: {e}", exc_info=True)


scheduler.add_job(
    func=_collect_and_push,
    trigger="interval",
    seconds=POLL_INTERVAL,
    id="collect_and_push",
    replace_existing=True,
)


# Daily cleanup: remove records older than 30 days
def _daily_cleanup():
    try:
        from myagentwatch.db import database

        cutoff = int(time.time() * 1000) - 30 * 86400 * 1000
        with database() as conn:
            conn.execute("DELETE FROM activity_log WHERE timestamp < ?", (cutoff,))
            conn.execute("DELETE FROM health_checks WHERE timestamp < ?", (cutoff,))
            conn.execute("DELETE FROM token_records WHERE timestamp < ?", (cutoff,))
            conn.execute("DELETE FROM tool_calls WHERE timestamp < ?", (cutoff,))
            conn.execute("VACUUM")
            conn.commit()
        logger.info("Daily cleanup complete")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


scheduler.add_job(
    func=_daily_cleanup,
    trigger="interval",
    hours=24,
    id="daily_cleanup",
    replace_existing=True,
)


# Agent dedup: merge duplicate agents (same name, different model_id)
def _dedup_agents():
    try:
        from myagentwatch.db import database

        with database() as conn:
            # Keep one agent per unique name, prefer those with model_id set
            conn.execute(
                """DELETE FROM agents WHERE id IN (
                    SELECT id FROM agents a1 WHERE EXISTS (
                        SELECT 1 FROM agents a2
                        WHERE a2.name = a1.name AND a2.model_id != '' AND a1.model_id = ''
                    )
                )"""
            )
            conn.commit()
        logger.info("Agent dedup complete")
    except Exception as e:
        logger.error(f"Dedup error: {e}")


scheduler.add_job(
    func=_dedup_agents,
    trigger="interval",
    hours=6,
    id="dedup_agents",
    replace_existing=True,
)
atexit.register(lambda: scheduler.shutdown())


# ---------- Main ----------
if __name__ == "__main__":
    logger.info(
        f"MyAgentWatch 2.0 starting on port {PORT}, poll every {POLL_INTERVAL}s"
    )

    discovered = collector.discover_all_agents()
    logger.info(f"Initial agent discovery: {len(discovered)} agents found")

    scheduler.start()
    logger.info("Background scheduler started")

    try:
        from waitress import serve

        logger.info(f"waitress serving on 0.0.0.0:{PORT}")
        serve(socketio.wsgi_app, host="0.0.0.0", port=PORT, threads=8)
    except (ImportError, AttributeError):
        logger.warning("waitress not available, falling back to werkzeug dev server")
        socketio.run(
            app, host="0.0.0.0", port=PORT, debug=False, allow_unsafe_werkzeug=True
        )
