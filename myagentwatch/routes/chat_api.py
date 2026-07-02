"""MyAgentWatch Chat API — 即时通讯 REST 端点。"""

import logging
import time

from flask import jsonify, request
from myagentwatch.db import database
from myagentwatch.queries import (
    query_chat_contacts,
    query_chat_conversations,
    query_chat_messages,
    query_chat_unread_total,
    query_or_create_conversation,
    insert_chat_message,
    mark_conversation_read,
)

logger = logging.getLogger("myagentwatch.chat")


def register_chat_routes(app, socketio):
    """注册聊天相关 API 路由。"""

    @app.route("/api/chat/conversations")
    def api_chat_conversations():
        with database() as conn:
            convs = query_chat_conversations(conn)
        return jsonify({"conversations": convs})

    @app.route("/api/chat/conversations", methods=["POST"])
    def api_chat_create_conversation():
        data = request.get_json(silent=True) or {}
        conv_type = data.get("type", "private")
        agent_id = data.get("agent_id")
        title = data.get("title", agent_id or "群聊")
        now = int(time.time() * 1000)
        with database() as conn:
            conv = query_or_create_conversation(conn, conv_type, agent_id, title, now)
        return jsonify({"conversation": conv})

    @app.route("/api/chat/messages/<int:conv_id>")
    def api_chat_messages(conv_id):
        before = request.args.get("before", type=int)
        limit = min(request.args.get("limit", 100, type=int), 200)
        with database() as conn:
            msgs = query_chat_messages(conn, conv_id, limit=limit, before_id=before)
        return jsonify({"messages": msgs})

    @app.route("/api/chat/messages/<int:conv_id>", methods=["POST"])
    def api_chat_send_message(conv_id):
        data = request.get_json(silent=True) or {}
        content = (data.get("message") or data.get("content") or "").strip()
        if not content:
            return jsonify({"error": "empty message"}), 400

        sender_type = data.get("sender_type", "human")
        sender_id = data.get("sender_id", "")
        sender_name = data.get("sender_name", "天宇")
        msg_type = data.get("msg_type", "text")
        reply_to = data.get("reply_to")
        now = int(time.time() * 1000)

        with database() as conn:
            msg = insert_chat_message(
                conn, conv_id, sender_type, sender_id, sender_name,
                content, msg_type, reply_to, now,
            )
        # WebSocket 广播给所有客户端
        socketio.emit("chat_message", {
            "conversation_id": conv_id,
            "message": msg,
            "timestamp": now,
        })
        return jsonify({"message": msg})

    @app.route("/api/chat/broadcast", methods=["POST"])
    def api_chat_broadcast():
        """群聊广播：消息发到群聊会话"""
        data = request.get_json(silent=True) or {}
        content = (data.get("message") or "").strip()
        if not content:
            return jsonify({"error": "empty message"}), 400

        sender_name = data.get("sender_name", "天宇")
        now = int(time.time() * 1000)
        with database() as conn:
            # 找到或创建群聊
            conv = conn.execute(
                "SELECT id FROM chat_conversations WHERE type='group' LIMIT 1"
            ).fetchone()
            if not conv:
                conn.execute(
                    "INSERT INTO chat_conversations (type, title, created_at) VALUES ('group', '群聊广播', ?)",
                    (now,),
                )
                conn.commit()
                conv = conn.execute(
                    "SELECT id FROM chat_conversations WHERE type='group' LIMIT 1"
                ).fetchone()

            msg = insert_chat_message(
                conn, conv["id"], "human", "", sender_name,
                content, "text", None, now,
            )
        socketio.emit("chat_message", {
            "conversation_id": conv["id"],
            "message": msg,
            "timestamp": now,
        })
        return jsonify({"message": msg})

    @app.route("/api/chat/contacts")
    def api_chat_contacts():
        with database() as conn:
            contacts = query_chat_contacts(conn)
        return jsonify({"contacts": contacts})

    @app.route("/api/chat/unread-count")
    def api_chat_unread_count():
        with database() as conn:
            total = query_chat_unread_total(conn)
        return jsonify({"unread_count": total})

    @app.route("/api/chat/read/<int:conv_id>", methods=["POST"])
    def api_chat_read(conv_id):
        with database() as conn:
            mark_conversation_read(conn, conv_id)
        return jsonify({"status": "ok"})
