"""Compute statistics from parsed session data."""

import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .parser import Session, Message

# Approximate pricing per 1M tokens (USD), as of mid-2026
# These are rough estimates; actual costs depend on plan/tier
PRICING = {
    # Claude models
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-fable-5": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    # Non-Claude models
    "gpt-5": {"input": 2.50, "output": 10.0, "cache_read": 0.25, "cache_write": 2.50},
    "minimax-m3:cloud": {"input": 1.20, "output": 4.80, "cache_read": 0.0, "cache_write": 0.0},
    "mimo-v2-flash": {"input": 0.15, "output": 0.60, "cache_read": 0.0, "cache_write": 0.0},
    "mimo-v2.5-pro": {"input": 0.43, "output": 1.70, "cache_read": 0.0, "cache_write": 0.0},
    "mimo-v2.5-free": {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0},
}

# Models known to be free — zero-cost pricing
FREE_MODELS = {
    "mimo-v2.5-free", "deepseek-v4-flash-free",
    "llama3.2:3b", "gemma4:latest", "qwen3-4b-base",
    "qwen3-4b-base:latest",
    "big-pickle",  # free on OpenCode Zen
    "unknown",     # unlabeled model
    "<synthetic>", # synthetic/test messages
    "mimo-auto",   # Mimo auto model router
}

# Routing / triage models — effectively zero cost
# Tuple passed to str.startswith() which accepts a tuple of prefixes
FREE_PREFIXES = ("triage-", "smarterrouter")

ZERO_PRICE = {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0}
DEFAULT_PRICE = {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75}


def _price_for(model: str) -> dict:
    """Get pricing for a model, checking free list and prefix matching."""
    if not model:
        return DEFAULT_PRICE
    # Exact match in pricing table
    if model in PRICING:
        return PRICING[model]
    # Known free models
    if model in FREE_MODELS:
        return ZERO_PRICE
    # Free-by-prefix (routers, triage models)
    if model.startswith(FREE_PREFIXES):
        return ZERO_PRICE
    # Prefix match in pricing table
    for prefix, price in sorted(PRICING.items(), key=lambda x: -len(x[0])):
        if model.startswith(prefix):
            return price
    return DEFAULT_PRICE


def _token_cost(tokens: int, price_per_m: float) -> float:
    return (tokens / 1_000_000) * price_per_m


@dataclass
class AggStats:
    """Aggregated statistics across all sessions."""
    total_sessions: int = 0
    total_messages: int = 0
    total_lines: int = 0
    total_size_mb: float = 0.0

    # Tokens
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    total_cache_create: int = 0

    # Cost
    estimated_cost: float = 0.0

    # Distributions
    model_counts: Counter = field(default_factory=Counter)
    stop_reasons: Counter = field(default_factory=Counter)
    msg_types: Counter = field(default_factory=Counter)
    tool_counts: Counter = field(default_factory=Counter)
    projects: Counter = field(default_factory=Counter)
    project_tokens: dict = field(default_factory=dict)  # project -> total tokens
    project_size: dict = field(default_factory=dict)  # project -> size in bytes
    project_sessions: dict = field(default_factory=dict)  # project -> [session_ids]

    # Session lengths (message counts)
    session_lengths: list = field(default_factory=list)

    # Source breakdown
    projects_source_count: int = 0
    local_agent_count: int = 0

    # Model-specific token breakdown
    model_input_tokens: dict = field(default_factory=dict)
    model_output_tokens: dict = field(default_factory=dict)
    model_costs: dict = field(default_factory=dict)  # model -> estimated cost in USD

    # Cache metrics
    cache_hit_ratio: float = 0.0

    # Per-project model distribution
    project_models: dict = field(default_factory=dict)


def _compute_model_costs(model_tokens_in, model_tokens_out, model_cache_read, model_cache_write):
    """Compute estimated cost per model from token counts."""
    model_cost_map = {}
    for model in set(list(model_tokens_in.keys()) + list(model_tokens_out.keys())):
        price = _price_for(model)
        cost = sum(_token_cost(t, price[k]) for k, t in [
            ("input", model_tokens_in.get(model, 0)),
            ("output", model_tokens_out.get(model, 0)),
            ("cache_read", model_cache_read.get(model, 0)),
            ("cache_write", model_cache_write.get(model, 0)),
        ])
        model_cost_map[model] = round(cost, 2)
    return {k: v for k, v in sorted(model_cost_map.items(), key=lambda x: -x[1])}


def compute_stats(sessions: list) -> AggStats:
    """Compute all statistics from a list of parsed Session objects."""
    stats = AggStats()
    stats.total_sessions = len(sessions)

    model_tokens_in = defaultdict(int)
    model_tokens_out = defaultdict(int)
    model_cache_read = defaultdict(int)
    model_cache_write = defaultdict(int)
    project_token_map = defaultdict(int)
    project_size_map = defaultdict(int)
    project_session_map = defaultdict(list)
    project_model_map = defaultdict(lambda: Counter())

    for sess in sessions:
        stats.total_lines += sess.line_count
        stats.total_messages += len(sess.messages)
        stats.session_lengths.append(len(sess.messages))

        if sess.source == "projects":
            stats.projects_source_count += 1
        else:
            stats.local_agent_count += 1

        stats.projects[sess.project] += 1
        project_session_map[sess.project].append(sess.session_id)

        try:
            fsize = os.path.getsize(sess.filepath)
            stats.total_size_mb += fsize / (1024 * 1024)
            project_size_map[sess.project] += fsize
        except OSError:
            pass

        for msg in sess.messages:
            stats.msg_types[msg.msg_type] += 1

            if msg.msg_type == "assistant":
                if msg.model:
                    stats.model_counts[msg.model] += 1
                    model_tokens_in[msg.model] += msg.input_tokens
                    model_tokens_out[msg.model] += msg.output_tokens
                    model_cache_read[msg.model] += msg.cache_read_tokens
                    model_cache_write[msg.model] += msg.cache_create_tokens
                    project_model_map[sess.project][msg.model] += 1

                stats.stop_reasons[msg.stop_reason or "?"] += 1
                stats.total_input_tokens += msg.input_tokens
                stats.total_output_tokens += msg.output_tokens
                stats.total_cache_read += msg.cache_read_tokens
                stats.total_cache_create += msg.cache_create_tokens
                project_token_map[sess.project] += msg.input_tokens + msg.output_tokens

                for tool in msg.tools_used:
                    stats.tool_counts[tool] += 1

                price = _price_for(msg.model or "")
                stats.estimated_cost += _token_cost(msg.input_tokens, price["input"])
                stats.estimated_cost += _token_cost(msg.output_tokens, price["output"])
                stats.estimated_cost += _token_cost(msg.cache_read_tokens, price["cache_read"])
                stats.estimated_cost += _token_cost(msg.cache_create_tokens, price["cache_write"])

    stats.model_input_tokens = dict(model_tokens_in)
    stats.model_output_tokens = dict(model_tokens_out)
    stats.model_costs = _compute_model_costs(model_tokens_in, model_tokens_out, model_cache_read, model_cache_write)
    stats.project_tokens = dict(project_token_map)
    stats.project_size = dict(project_size_map)
    stats.project_sessions = dict(project_session_map)
    stats.project_models = {k: dict(v) for k, v in project_model_map.items()}

    total_context = stats.total_input_tokens + stats.total_cache_read + stats.total_cache_create
    if total_context > 0:
        stats.cache_hit_ratio = stats.total_cache_read / total_context * 100

    return stats


def aggregate_message_stats(messages: list) -> dict:
    """Extract model, tool, token, and stop-reason stats from a message list.

    Returns a dict with:
        models (Counter), tools (Counter), stop_reasons (Counter),
        total_input_tokens, total_output_tokens, total_cache_read, total_cache_write

    Shared entry point used by both stats.py and diff.py to avoid duplicating
    the message-aggregation loop.
    """
    from collections import Counter

    models = Counter()
    tools = Counter()
    stop_reasons = Counter()
    t_in = 0
    t_out = 0
    t_cache_r = 0
    t_cache_w = 0

    for msg in messages:
        if msg.msg_type != "assistant":
            continue
        if msg.model:
            models[msg.model] += 1
        t_in += msg.input_tokens
        t_out += msg.output_tokens
        t_cache_r += msg.cache_read_tokens
        t_cache_w += msg.cache_create_tokens
        stop_reasons[msg.stop_reason or "?"] += 1
        for tool in msg.tools_used:
            tools[tool] += 1

    return {
        "models": models,
        "tools": tools,
        "stop_reasons": stop_reasons,
        "total_input_tokens": t_in,
        "total_output_tokens": t_out,
        "total_cache_read": t_cache_r,
        "total_cache_write": t_cache_w,
    }


def format_number(n: int) -> str:
    """Format large numbers with commas."""
    return f"{n:,}"


def format_tokens(n: int) -> str:
    """Format token counts with appropriate suffix."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_bytes(n: int) -> str:
    """Format byte counts."""
    if n >= 1073741824:
        return f"{n / 1073741824:.1f}GiB"
    if n >= 1048576:
        return f"{n / 1048576:.0f}MiB"
    if n >= 1024:
        return f"{n / 1024:.0f}KiB"
    return f"{n}B"
