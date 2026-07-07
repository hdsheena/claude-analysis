"""Time-series analysis for Claude session data."""

import json
import os
import glob
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from .parser import Session


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
    """Convert epoch seconds to YYYY-MM-DD."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _week_key(ts: float) -> str:
    """Convert epoch seconds to YYYY-Www."""
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-W%U")


def _month_key(ts: float) -> str:
    """Convert epoch seconds to YYYY-MM."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m")


def compute_timeline(sessions: list, bucket: str = "daily") -> dict:
    """Compute time-series aggregates from sessions.

    Args:
        sessions: list of Session objects
        bucket: "daily", "weekly", or "monthly"

    Returns:
        dict with keys: dates (list), tokens (list), sessions (list), models (dict of lists)
    """
    key_fn = {"daily": _day_key, "weekly": _week_key, "monthly": _month_key}[bucket]

    # Collect data per time bucket
    buckets = defaultdict(lambda: {
        "tokens": 0, "sessions": set(), "messages": 0,
        "models": defaultdict(int), "cost": 0.0,
    })

    registry = {}
    for f in glob.glob(os.path.expanduser("~/.claude/sessions/*.json")):
        try:
            d = json.load(open(f))
            sid = d.get("sessionId")
            ts = d.get("startedAt")
            if sid and ts:
                registry[sid] = _parse_ts(ts)
        except Exception:
            pass

    from .stats import _price_for, _token_cost

    for sess in sessions:
        # Find timestamp from registry or first message
        ts = registry.get(sess.session_id)
        if ts is None and sess.messages:
            # Try to get timestamp from first message
            for msg in sess.messages:
                # We don't have raw timestamps in Message objects yet —
                # use session-level approximation
                pass

        if ts is None:
            continue

        key = key_fn(ts)
        bucket_data = buckets[key]
        bucket_data["sessions"].add(sess.session_id)

        for msg in sess.messages:
            if msg.msg_type == "assistant":
                bucket_data["tokens"] += msg.input_tokens + msg.output_tokens
                bucket_data["messages"] += 1
                if msg.model:
                    bucket_data["models"][msg.model] += 1
                price = _price_for(msg.model or "")
                bucket_data["cost"] += _token_cost(msg.input_tokens, price["input"])
                bucket_data["cost"] += _token_cost(msg.output_tokens, price["output"])
                bucket_data["cost"] += _token_cost(msg.cache_read_tokens, price["cache_read"])
                bucket_data["cost"] += _token_cost(msg.cache_create_tokens, price["cache_write"])

    # Sort and build output
    sorted_keys = sorted(buckets.keys())
    return {
        "dates": sorted_keys,
        "tokens": [buckets[k]["tokens"] for k in sorted_keys],
        "sessions": [len(buckets[k]["sessions"]) for k in sorted_keys],
        "cost": [round(buckets[k]["cost"], 2) for k in sorted_keys],
        "top_models": _top_models_over_time(buckets, sorted_keys),
        "bucket": bucket,
    }


def _top_models_over_time(buckets: dict, sorted_keys: list) -> dict:
    """Track top models over time."""
    all_models = set()
    for k in sorted_keys:
        all_models.update(buckets[k]["models"].keys())
    # Top 5 overall
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

    # Unicode block gradient: low to high density
    blocks = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    # Downsample to fit width
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

    # Per-model sparklines
    if tl["top_models"]:
        lines.append("")
        lines.append("  Model usage over time:")
        for model, vals in tl["top_models"].items():
            short = model.replace("claude-", "")[:25]
            lines.append(sparkline(vals, label=short))

    # Detailed table for last N periods
    lines.append("")
    lines.append(f"  {'Period':<12} {'Tokens':>12} {'Sessions':>10} {'Cost':>10}")
    lines.append("  " + "─" * 48)
    for i in range(max(0, len(tl["dates"]) - 20), len(tl["dates"])):
        d = tl["dates"][i]
        t = f"{tl['tokens'][i]:,}"
        s = tl["sessions"][i]
        c = f"\${tl['cost'][i]:.2f}"
        lines.append(f"  {d:<12} {t:>12} {s:>10} {c:>10}")

    return "\n".join(lines)
