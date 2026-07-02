"""MyAgentWatch — Model pricing table with seed data and cost calculation.

Covers 8 providers: Anthropic, OpenAI, DeepSeek, Qwen, Kimi/Moonshot,
GLM (Zhipu), Doubao, and custom user-defined entries.

Prices are per MILLION tokens (USD). Domestic model prices converted
from CNY at approximate exchange rates. Verify periodically against
official pricing pages.
"""

import time

# All prices in USD per 1M tokens.
# cache_write defaults to 1.25× input (Anthropic convention);
# cache_read defaults to 0.10× input (Anthropic convention).
SEED_PRICING = [
    # ── Anthropic ──
    ("anthropic", "claude-opus-4-7", "Claude Opus 4.7", 5, 25, 0.50, 6.25),
    ("anthropic", "claude-opus-4-6", "Claude Opus 4.6", 5, 25, 0.50, 6.25),
    ("anthropic", "claude-opus-4-5", "Claude Opus 4.5", 5, 25, 0.50, 6.25),
    ("anthropic", "claude-sonnet-4-6", "Claude Sonnet 4.6", 3, 15, 0.30, 3.75),
    ("anthropic", "claude-sonnet-4-5", "Claude Sonnet 4.5", 3, 15, 0.30, 3.75),
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5", 1, 5, 0.10, 1.25),
    ("anthropic", "claude-haiku-3-5", "Claude Haiku 3.5", 0.80, 4, 0.08, 1.00),
    ("anthropic", "claude-opus-4-1", "Claude Opus 4.1 (legacy)", 15, 75, 1.50, 18.75),

    # ── OpenAI ──
    ("openai", "gpt-5.5", "GPT-5.5", 5, 30, 0.50, 5),
    ("openai", "gpt-5.4", "GPT-5.4", 2.50, 15, 0.25, 2.50),
    ("openai", "gpt-5.4-mini", "GPT-5.4 mini", 0.75, 4.50, 0.075, 0.75),
    ("openai", "gpt-5.4-nano", "GPT-5.4 nano", 0.20, 1.25, 0.02, 0.20),
    ("openai", "gpt-5", "GPT-5", 1.25, 10, 0.125, 1.25),
    ("openai", "gpt-5-mini", "GPT-5 mini", 0.25, 2, 0.025, 0.25),
    ("openai", "gpt-5-nano", "GPT-5 nano", 0.05, 0.40, 0.005, 0.05),
    ("openai", "gpt-4o", "GPT-4o", 2.50, 10, 1.25, 2.50),
    ("openai", "gpt-4o-mini", "GPT-4o mini", 0.15, 0.60, 0.075, 0.15),
    ("openai", "o4-mini", "o4-mini", 1.10, 4.40, 0.275, 1.10),
    ("openai", "o3", "o3", 2, 8, 0.50, 2),
    ("openai", "o3-mini", "o3-mini", 1.10, 4.40, 0.55, 1.10),

    # ── DeepSeek ── (USD, approximate)
    ("deepseek", "deepseek-chat", "DeepSeek V3", 0.27, 1.10, 0.07, 0.27),
    ("deepseek", "deepseek-reasoner", "DeepSeek R1", 0.55, 2.19, 0.14, 0.55),
    ("deepseek", "deepseek-v4", "DeepSeek V4", 0.20, 0.80, 0.05, 0.20),
    ("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro", 0.30, 1.50, 0.08, 0.30),
    ("deepseek", "deepseek-v4-flash", "DeepSeek V4 Flash", 0.10, 0.40, 0.03, 0.10),

    # ── Qwen / Tongyi ── (USD, from CNY ~¥0.5-15/1M tokens)
    ("qwen", "qwen-max", "Qwen Max", 2.10, 6.30, 0, 0),
    ("qwen", "qwen-plus", "Qwen Plus", 1.10, 3.30, 0, 0),
    ("qwen", "qwen-turbo", "Qwen Turbo", 0.40, 1.20, 0, 0),
    ("qwen", "qwen3-235b", "Qwen3 235B", 1.40, 4.20, 0, 0),

    # ── Kimi / Moonshot ── (USD, from CNY)
    ("moonshot", "moonshot-v1-8k", "Moonshot v1 8K", 1.40, 5.60, 0, 0),
    ("moonshot", "moonshot-v1-32k", "Moonshot v1 32K", 3.20, 12.80, 0, 0),
    ("moonshot", "kimi-latest", "Kimi Latest", 1.40, 5.60, 0, 0),

    # ── GLM / Zhipu ── (USD, from CNY ¥0.01-0.10/1K tokens)
    ("zhipu", "glm-4-plus", "GLM-4 Plus", 2.10, 2.10, 0, 0),
    ("zhipu", "glm-4-flash", "GLM-4 Flash", 0.14, 0.14, 0, 0),
    ("zhipu", "glm-4-air", "GLM-4 Air", 0.07, 0.07, 0, 0),

    # ── Doubao / ByteDance ── (USD, from CNY)
    ("doubao", "doubao-pro-32k", "Doubao Pro 32K", 0.28, 0.84, 0, 0),
    ("doubao", "doubao-lite-32k", "Doubao Lite 32K", 0.11, 0.33, 0, 0),
]


def seed_pricing(conn) -> int:
    """Insert default pricing rows (idempotent). Returns number inserted."""
    now_ms = int(time.time() * 1000)
    count = 0
    for provider, model, name, inp, outp, cr, cw in SEED_PRICING:
        cur = conn.execute(
            "SELECT id FROM pricing WHERE provider_id = ? AND model_id = ?",
            (provider, model),
        )
        if cur.fetchone() is None:
            conn.execute(
                "INSERT INTO pricing (provider_id, model_id, display_name, "
                "price_per_1m_input, price_per_1m_output, "
                "price_per_1m_cache_read, price_per_1m_cache_write, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (provider, model, name, inp, outp, cr, cw, now_ms),
            )
            count += 1
    return count


def load_pricing(conn) -> dict[str, dict]:
    """Load active pricing rows into a dict keyed by model_id.

    Returns: {model_id: {input, output, cache_read, cache_write, provider, name}}
    """
    rows = conn.execute(
        "SELECT model_id, provider_id, display_name, "
        "price_per_1m_input, price_per_1m_output, "
        "price_per_1m_cache_read, price_per_1m_cache_write "
        "FROM pricing WHERE is_active = 1"
    ).fetchall()
    table = {}
    for r in rows:
        table[r["model_id"]] = {
            "input": r["price_per_1m_input"],
            "output": r["price_per_1m_output"],
            "cache_read": r["price_per_1m_cache_read"],
            "cache_write": r["price_per_1m_cache_write"],
            "provider": r["provider_id"],
            "name": r["display_name"],
        }
    return table


def calculate_cost(model_id: str, inp_tokens: int, out_tokens: int,
                   cache_read: int = 0, cache_write: int = 0,
                   table: dict = None) -> float:
    """Calculate USD cost for token usage.

    Uses the same formula as Multica: sum(token * price) / 1M.
    Falls back to hardcoded Claude Sonnet pricing if model not found.
    """
    if table is None:
        table = {}
    p = table.get(model_id)
    if p is None:
        # Fallback: Claude Sonnet 4.x default
        p = {"input": 3, "output": 15, "cache_read": 0.30, "cache_write": 3.75}
    return (
        inp_tokens * p["input"]
        + out_tokens * p["output"]
        + cache_read * p["cache_read"]
        + cache_write * p["cache_write"]
    ) / 1_000_000.0
