"""Time-series analysis for Claude session data."""

import json
import os
import glob
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from .parser import Session
from .stats import _price_for, _token_cost


def _parse_ts(val) -> Optional[float]:
    """Parse timestamp from various formats."""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val) / 1000.0 if val > 1e12 else float(val)
        if isinstance(val, str):
            return float(val) / 1000.0 if float(val) > 1e12 else float(val)
    except (ValueError, TypeError):
        pass
    return None


def _day_key(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _week_key(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    mon = dt - timedelta(days=dt.weekday())
    return mon.strftime("%Y-%m-%d")


def _month_key(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m")


def _load_registry() -> dict:
    """Load session timestamp registry from ~/.claude/sessions/*.json."""
    registry = {}
    for f in glob.glob(os.path.expanduser("~/.claude/sessions/*.json")):
        try:
            d = json.load(open(f))
            sid = d.get("sessionId")
            ts = d.get("startedAt")
            if sid and ts:
                registry[sid] = _parse_ts(ts)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return registry


def _compute_buckets(sessions: list, key_fn, registry: dict) -> dict:
    """Build per-time-bucket aggregate dicts from sessions."""
    buckets = defaultdict(lambda: {
        "tokens": 0, "sessions": set(), "messages": 0,
        "models": defaultdict(int), "cost": 0.0,
        "cache_read": 0, "cache_write": 0,
        "tokens_by_source": defaultdict(int),
    })

    for sess in sessions:
        ts = registry.get(sess.session_id) or _parse_ts(sess.started_at)
        if ts is None:
            continue

        display_source = sess.source
        if display_source in ("projects", "local-agent"):
            display_source = "claude"

        key = key_fn(ts)
        bucket_data = buckets[key]
        bucket_data["sessions"].add(sess.session_id)

        for msg in sess.messages:
            if msg.msg_type != "assistant":
                continue
            msg_tokens = msg.input_tokens + msg.output_tokens
            bucket_data["tokens"] += msg_tokens
            bucket_data["tokens_by_source"][display_source] += msg_tokens
            bucket_data["messages"] += 1
            if msg.model:
                bucket_data["models"][msg.model] += 1
            bucket_data["cache_read"] += msg.cache_read_tokens
            bucket_data["cache_write"] += msg.cache_create_tokens
            price = _price_for(msg.model or "")
            bucket_data["cost"] += sum(
                _token_cost(t, p) for t, p in [
                    (msg.input_tokens, price["input"]),
                    (msg.output_tokens, price["output"]),
                    (msg.cache_read_tokens, price["cache_read"]),
                    (msg.cache_create_tokens, price["cache_write"]),
                ]
            )

    return buckets


def _build_timeline_output(buckets: dict, sorted_keys: list, bucket: str) -> dict:
    """Build the output dict from computed buckets."""
    all_sources = set()
    for k in sorted_keys:
        all_sources.update(buckets[k]["tokens_by_source"].keys())
    tokens_by_source = {
        src: [buckets[k]["tokens_by_source"].get(src, 0) for k in sorted_keys]
        for src in sorted(all_sources)
    }

    return {
        "dates": sorted_keys,
        "tokens": [buckets[k]["tokens"] for k in sorted_keys],
        "tokens_by_source": tokens_by_source,
        "sessions": [len(buckets[k]["sessions"]) for k in sorted_keys],
        "cost": [round(buckets[k]["cost"], 2) for k in sorted_keys],
        "cache_read": [buckets[k]["cache_read"] for k in sorted_keys],
        "cache_write": [buckets[k]["cache_write"] for k in sorted_keys],
        "top_models": _top_models_over_time(buckets, sorted_keys),
        "bucket": bucket,
    }


def compute_timeline(sessions: list, bucket: str = "daily") -> dict:
    """Compute time-series aggregates from sessions.

    Args:
        sessions: list of Session objects
        bucket: "daily", "weekly", or "monthly"

    Returns:
        dict with dates, tokens, sessions, models lists, etc.
    """
    key_fn = {"daily": _day_key, "weekly": _week_key, "monthly": _month_key}[bucket]
    registry = _load_registry()
    buckets = _compute_buckets(sessions, key_fn, registry)
    sorted_keys = sorted(buckets.keys())
    return _build_timeline_output(buckets, sorted_keys, bucket)


def _top_models_over_time(buckets: dict, sorted_keys: list) -> dict:
    """Track top 5 models over time."""
    totals = defaultdict(int)
    for k in sorted_keys:
        for m, c in buckets[k]["models"].items():
            totals[m] += c
    top_5 = [m for m, _ in sorted(totals.items(), key=lambda x: -x[1])[:5]]

    result = {}
    for model in top_5:
        result[model] = [buckets[k]["models"].get(model, 0) for k in sorted_keys]
    return result


def sparkline(values: list, width: int = 40, label: str = "") -> str:
    """Render a sparkline (unicode block chars) for a list of numeric values."""
    if not values:
        return f"{label:<12} (no data)"

    min_v = min(values)
    max_v = max(values)
    span = max_v - min_v if max_v != min_v else 1

    blocks = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    n = len(values)
    if n > width:
        step = n / width
        sampled = []
        for i in range(width):
            start = int(i * step)
            end = int((i + 1) * step)
            chunk = values[start:end]
            sampled.append(sum(chunk) / len(chunk) if chunk else 0)
        values = sampled

    chars = []
    for v in values:
        idx = int((v - min_v) / span * (len(blocks) - 1))
        chars.append(blocks[min(idx, len(blocks) - 1)])

    line = "".join(chars)
    return f"{label:<12} {min_v:>10,.0f} {line} {max_v:>10,.0f}"


def timeline_report(sessions: list, bucket: str = "daily") -> str:
    """Generate a time-series report with sparklines."""
    tl = compute_timeline(sessions, bucket)

    lines = []
    lines.append(f"\n┌─ TIME-SERIES ({bucket.upper()}) {'─' * 40}┐")
    lines.append(f"  Periods: {len(tl['dates'])}")

    if tl["dates"]:
        lines.append(f"  Range: {tl['dates'][0]} → {tl['dates'][-1]}")
    lines.append("  Note: dates are approximate (session start time from registry).")
    lines.append("  Sessions without registry entries may be excluded.")

    lines.append("")
    lines.append(sparkline(tl["tokens"], label="Tokens"))
    lines.append(sparkline(tl["sessions"], label="Sessions"))
    lines.append(sparkline(tl["cost"], label="Cost ($)"))

    if tl["top_models"]:
        lines.append("")
        lines.append("  Model usage over time:")
        for model, vals in tl["top_models"].items():
            short = model.replace("claude-", "")[:25]
            lines.append(sparkline(vals, label=short))

    lines.append("")
    lines.append(f"  {'Period':<12} {'Tokens':>12} {'Sessions':>10} {'Cost':>10}")
    lines.append("  " + "─" * 48)
    for i in range(max(0, len(tl["dates"]) - 20), len(tl["dates"])):
        d = tl["dates"][i]
        t = f"{tl['tokens'][i]:,}"
        s = tl["sessions"][i]
        c = f"${tl['cost'][i]:.2f}"
        lines.append(f"  {d:<12} {t:>12} {s:>10} {c:>10}")

    return "\n".join(lines)
