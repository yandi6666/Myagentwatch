"""LogCompiler — 将对话 Turn 导出为 Markdown / JSON 格式。

替代人工手写 changelog，程序化生成结构化日志报告。
"""

import json
import time
from datetime import datetime, timezone


def _fmt_time(epoch_ms: int) -> str:
    """将 epoch 毫秒转为可读时间字符串。"""
    if not epoch_ms:
        return "?"
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_time_short(epoch_ms: int) -> str:
    """短格式：HH:MM:SS.mmm"""
    if not epoch_ms:
        return "??:??:??"
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%H:%M:%S") + f".{epoch_ms % 1000:03d}"


def _phase_emoji(phase: str) -> str:
    mapping = {
        "thinking": "💭",
        "tool_call": "🔧",
        "tool_result": "📋",
        "handoff": "🔀",
        "handoff_result": "🔙",
        "response": "💬",
        "instruction": "👤",
        "error": "🚨",
        "heartbeat": "💓",
    }
    return mapping.get(phase, "📌")


def _severity_marker(severity: str) -> str:
    if severity in ("error", "critical"):
        return "🔴"
    if severity == "warn":
        return "🟡"
    return ""


def turns_to_markdown(turns: list[dict]) -> str:
    """将 Turn 列表导出为 Markdown 格式。

    :param turns: query_turns() 返回的 dict 列表
    """
    if not turns:
        return "# 日志报告\n\n无数据。"

    now = _fmt_time(int(time.time() * 1000))
    lines = [
        f"# MyAgentWatch 日志报告",
        f"",
        f"> 导出时间: {now}",
        f"> 日志条数: {len(turns)}",
        f"",
        f"---",
        f"",
    ]

    # 按 session 分组
    sessions: dict[str, list[dict]] = {}
    for t in turns:
        sid = t.get("session_id", "unknown")
        if sid not in sessions:
            sessions[sid] = []
        sessions[sid].append(t)

    for sid, session_turns in sessions.items():
        session_turns.sort(key=lambda t: t.get("time_start", 0))
        first_ts = session_turns[0].get("time_start", 0) if session_turns else 0

        lines.append(f"## 会话 `{sid[:12]}...`")
        lines.append(f"")
        lines.append(f"**时间**: {_fmt_time(first_ts)}")
        lines.append(f"**Turn 数**: {len(session_turns)}")
        lines.append(f"")

        for t in session_turns:
            phase = t.get("phase", "")
            ts = t.get("time_start", 0)
            severity = t.get("severity", "info")
            marker = _severity_marker(severity)
            emoji = _phase_emoji(phase)

            agent = t.get("agent_id", "?")
            if "::" in agent:
                parts = agent.split("::")
                agent = f"{parts[-2]} ({parts[-1]})" if len(parts) >= 6 else agent

            content = t.get("content_preview", "") or ""
            if len(content) > 200:
                content = content[:200] + "..."

            lines.append(f"### Turn {t.get('seq', '?')} — {_fmt_time_short(ts)} {marker}")
            lines.append(f"")
            lines.append(f"| 字段 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| Agent | {agent} |")
            lines.append(f"| 阶段 | {emoji} {phase} |")
            lines.append(f"| 来源 | {t.get('source_type', '?')} |")
            if content:
                lines.append(f"| 内容 | {content} |")

            trace_id = t.get("trace_id", "")
            if trace_id:
                lines.append(f"| 追踪ID | `{trace_id[:16]}...` |")

            lines.append(f"")

        lines.append(f"---")
        lines.append(f"")

    return "\n".join(lines)


def turns_to_json(turns: list[dict], pretty: bool = True) -> str:
    """将 Turn 列表导出为 JSON 字符串。"""
    indent = 2 if pretty else None
    return json.dumps(
        {
            "exported_at": _fmt_time(int(time.time() * 1000)),
            "total": len(turns),
            "turns": turns,
        },
        ensure_ascii=False,
        indent=indent,
    )
