"""Usage burn-rate and pacing analysis.

Computes per-source usage burn over trailing windows (hours/days/weeks/months)
and projects it forward: month-to-date totals, projected month-end at the recent
30-day pace, month-over-month pace change, hourly-of-day distribution, and (when
caps are configured) estimated remaining usage and days left.

Metric per source:
  - "tokens":   input + output + cache_read + cache_write for every source with
                token data (claude/projects/local-agent, mimo, opencode, codex)
  - "requests": number of AI calls (assistant messages) for sources without
                token data (Copilot, Freebuff, Antigravity)

Optional caps live in a JSON file (default ~/.config/claude-analysis/caps.json):

    {
      "codex":   {"metric": "tokens",   "cap": 200000000, "period": "week"},
      "copilot": {"metric": "requests", "cap": 2000,      "period": "month"}
    }

`period` is "week" (Mon-Sun) or "month". A "month" cap is the calendar month by
default; add `"reset_day": <1-31>` to anchor it to a billing-cycle anniversary
(e.g. GitHub Copilot and OpenAI Codex allowances reset on the subscription
renewal day, not the 1st). The window clamps reset_day to the length of each
month. "days left" is remaining usage divided by the recent 30-day average
daily burn — a guess, not a quota API. Server-side limits (e.g. Claude's 5x,
measured by Anthropic) have no local source of truth, so anything without a
configured cap is pace-only.
"""

import calendar
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from .parser import Session
from .stats import format_tokens
from .timeline import _load_registry, _parse_ts, sparkline

METRIC_TOKENS = "tokens"
METRIC_REQUESTS = "requests"

TOKEN_SOURCES = {"claude", "projects", "local-agent", "mimo", "opencode", "codex"}
REQUEST_SOURCES = {"copilot", "freebuff", "antigravity"}

DEFAULT_CAPS_PATH = os.path.expanduser("~/.config/claude-analysis/caps.json")


def source_metric(source: str) -> str:
    """Return the burn metric ('tokens' or 'requests') for a source."""
    return METRIC_TOKENS if source in TOKEN_SOURCES else METRIC_REQUESTS


def _session_value(sess: Session) -> int:
    """Total metric value for a session: tokens or assistant-message count."""
    if sess.source in TOKEN_SOURCES:
        total = 0
        for m in sess.messages:
            if m.msg_type == "assistant":
                total += (m.input_tokens + m.output_tokens
                          + m.cache_read_tokens + m.cache_create_tokens)
        return total
    return sum(1 for m in sess.messages if m.msg_type == "assistant")


def _days_in_month(dt: date) -> int:
    return calendar.monthrange(dt.year, dt.month)[1]


def _cycle_bounds(today: date, reset_day: Optional[int]) -> tuple:
    """Return (start, end_exclusive) of the current month usage window.

    reset_day None → the calendar month. Otherwise the billing cycle anchored
    on that day of month (e.g. reset_day=26 on Aug 6 → Jul 26 .. Aug 26),
    clamping reset_day to the length of each month.
    """
    if not isinstance(reset_day, int) or not (1 <= reset_day <= 31):
        start = today.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, end

    def _clamped(y: int, m: int) -> int:
        return min(reset_day, calendar.monthrange(y, m)[1])

    if today.day >= _clamped(today.year, today.month):
        start = today.replace(day=_clamped(today.year, today.month))
    else:
        py, pm = (today.year, today.month - 1) if today.month > 1 \
            else (today.year - 1, 12)
        start = today.replace(year=py, month=pm, day=_clamped(py, pm))
    ey, em = (start.year, start.month + 1) if start.month < 12 \
        else (start.year + 1, 1)
    end = start.replace(year=ey, month=em, day=_clamped(ey, em))
    return start, end


def _window_sum(days: dict, today_dt: date, n: int) -> int:
    """Sum daily values for the trailing n days (inclusive of today)."""
    cutoff = (today_dt - timedelta(days=n)).strftime("%Y-%m-%d")
    return sum(v for d, v in days.items() if d >= cutoff)


def compute_source_burns(sessions: list, now: Optional[float] = None) -> dict:
    """Compute per-source burn stats keyed by source name.

    Only sources with at least one timestamped, non-zero session appear.
    """
    now = now if now is not None else datetime.now().timestamp()
    registry = _load_registry()
    today_dt = datetime.fromtimestamp(now).date()
    this_month = today_dt.strftime("%Y-%m")
    last_month_dt = today_dt.replace(day=1) - timedelta(days=1)
    last_month = last_month_dt.strftime("%Y-%m")
    days_in_month = _days_in_month(today_dt)
    last_month_days = _days_in_month(last_month_dt)
    cutoff_30 = now - 30 * 86400

    by_day = defaultdict(lambda: defaultdict(int))
    by_month = defaultdict(lambda: defaultdict(int))
    by_hour = defaultdict(lambda: defaultdict(int))
    undated = 0

    for sess in sessions:
        ts = registry.get(sess.session_id) or _parse_ts(sess.started_at)
        if ts is None:
            undated += 1
            continue
        value = _session_value(sess)
        if value == 0:
            continue
        dt = datetime.fromtimestamp(ts)
        src = sess.source
        by_day[src][dt.strftime("%Y-%m-%d")] += value
        by_month[src][dt.strftime("%Y-%m")] += value
        if ts >= cutoff_30:
            by_hour[src][dt.hour] += value

    burns = {}
    for src, days in sorted(by_day.items()):
        months = by_month[src]
        mtd = months.get(this_month, 0)
        last_month_total = months.get(last_month, 0)
        last_month_avg = last_month_total / last_month_days
        mtd_avg = mtd / max(today_dt.day, 1)
        pace = ((mtd_avg - last_month_avg) / last_month_avg * 100
                if last_month_avg > 0 else None)
        avg30 = _window_sum(days, today_dt, 30) / 30.0
        burns[src] = {
            "source": src,
            "metric": source_metric(src),
            "has_data": sum(days.values()) > 0,
            "days": dict(sorted(days.items())),
            "today": days.get(today_dt.strftime("%Y-%m-%d"), 0),
            "last7": _window_sum(days, today_dt, 7),
            "last30": _window_sum(days, today_dt, 30),
            "last90": _window_sum(days, today_dt, 90),
            "avg7": _window_sum(days, today_dt, 7) / 7.0,
            "avg30": avg30,
            "avg90": _window_sum(days, today_dt, 90) / 90.0,
            "mtd": mtd,
            "mtd_days": today_dt.day,
            "days_in_month": days_in_month,
            "proj_month_end": int(mtd + avg30 * (days_in_month - today_dt.day)),
            "last_month": last_month_total,
            "last_month_avg": last_month_total / last_month_days,
            "pace_change_pct": round(pace, 1) if pace is not None else None,
            "hourly": dict(sorted(by_hour[src].items())),
            "undated_skipped": undated,
        }
    return burns


def load_caps(path: Optional[str] = None) -> dict:
    """Load the caps JSON file; empty dict if missing or malformed."""
    p = path or DEFAULT_CAPS_PATH
    try:
        with open(p) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_caps(caps: dict, path: Optional[str] = None) -> str:
    """Write caps to disk, returning the path written."""
    p = path or DEFAULT_CAPS_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(caps, f, indent=2, sort_keys=True)
    return p


def project_caps(burns: dict, caps: dict, now: Optional[float] = None) -> list:
    """Estimate remaining usage and days left for each configured cap.

    Projection uses the recent 30-day average daily burn, not the period's own
    (noisy, early-window) average.
    """
    now = now if now is not None else datetime.now().timestamp()
    today_dt = datetime.fromtimestamp(now).date()
    mon = today_dt - timedelta(days=today_dt.weekday())

    out = []
    for src, cfg in sorted(caps.items()):
        burn = burns.get(src)
        if burn is None or burn["metric"] != cfg.get("metric"):
            continue
        cap = cfg.get("cap")
        period = cfg.get("period", "month")
        reset_day = cfg.get("reset_day")
        rd = reset_day if isinstance(reset_day, int) and 1 <= reset_day <= 31 \
            else None
        if not isinstance(cap, (int, float)) or cap <= 0:
            continue
        avg30 = burn["avg30"]
        if period == "week":
            start, end = mon, mon + timedelta(days=7)
        else:
            start, end = _cycle_bounds(today_dt, rd)
        start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        used = sum(v for d, v in burn["days"].items()
                   if start_s <= d < end_s)
        remaining_days = max((end - today_dt).days - 1, 0)
        projected = int(used + avg30 * remaining_days)
        remaining = max(0, cap - used)
        days_left = remaining / avg30 if avg30 > 0 else None
        exhausted = avg30 > 0 and projected > cap
        out.append({
            "source": src,
            "metric": burn["metric"],
            "period": period,
            "reset_day": rd if period == "month" else None,
            "cycle_start": start_s,
            "cycle_end": end_s,
            "cap": int(cap),
            "used": int(used),
            "projected": projected,
            "pct_used": round(used / cap * 100, 1),
            "remaining": int(remaining),
            "avg30": avg30,
            "days_left": round(days_left, 1) if days_left is not None else None,
            "projected_over_cap": bool(exhausted),
            "est_exhaust_date": (
                (today_dt + timedelta(days=math.ceil(days_left))).strftime("%Y-%m-%d")
                if exhausted and days_left is not None else None
            ),
        })
    return out


def _fmt(v, metric: str) -> str:
    if metric == METRIC_TOKENS:
        return format_tokens(int(v))
    return f"{int(v):,}"


def _pace_str(burn: dict) -> str:
    p = burn["pace_change_pct"]
    return "—" if p is None else f"{p:+.0f}%"


def _hour_bars(hourly: dict) -> str:
    values = [hourly.get(h, 0) for h in range(24)]
    mx = max(values) or 1
    blocks = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    return "".join(blocks[min(int(v / mx * 8), 8)] for v in values)


def _span(burns: dict) -> tuple:
    all_days = set()
    for b in burns.values():
        all_days.update(b["days"].keys())
    if not all_days:
        return None
    return min(all_days), max(all_days)


def usage_report(sessions: list, caps: Optional[dict] = None,
                 now: Optional[float] = None) -> str:
    """Render the CLI usage/pacing report."""
    now = now if now is not None else datetime.now().timestamp()
    burns = compute_source_burns(sessions, now)
    caps = caps if caps is not None else load_caps()
    proj = project_caps(burns, caps, now)
    today_dt = datetime.fromtimestamp(now).date()

    lines = []
    lines.append(f"\n┌─ USAGE & PACING {'─' * 48}┐")
    span = _span(burns)
    if span:
        lines.append(f"  Window: {span[0]} → {span[1]}")
    lines.append("  Metric: tokens = input+output+cache · requests = AI calls")
    lines.append("         (Copilot/Freebuff/Antigravity have no token data)")
    lines.append("")

    hdr = ("  {:<13}{:<9}{:>9}{:>10}{:>10}{:>10}{:>12}{:>11}{:>11}{:>8}").format(
        "SOURCE", "METRIC", "TODAY", "AVG/7D", "AVG/30D", "AVG/90D",
        "MTD", "PROJ-MO", "LAST-MO", "Δ/MO")
    lines.append(hdr)
    lines.append("  " + "─" * 102)
    for src, b in sorted(burns.items()):
        m = b["metric"]
        lines.append(("  {:<13}{:<9}{:>9}{:>10}{:>10}{:>10}{:>12}{:>11}{:>11}{:>8}").format(
            src[:12], m, _fmt(b["today"], m), _fmt(b["avg7"], m),
            _fmt(b["avg30"], m), _fmt(b["avg90"], m), _fmt(b["mtd"], m),
            _fmt(b["proj_month_end"], m), _fmt(b["last_month"], m), _pace_str(b)))

    lines.append("")
    if proj:
        lines.append("  ── QUOTA CAPS (days left at recent 30-day pace) ──")
        for p in proj:
            status = "EXCEEDS CAP" if p["projected_over_cap"] else "on pace"
            period = p["period"]
            if period == "month" and p["reset_day"]:
                period = f"month(reset@{p['reset_day']})"
            lines.append(
                f"  {p['source'][:12]:<12} {p['metric']:<8} {period:<16} "
                f"used {_fmt(p['used'], p['metric'])} / {_fmt(p['cap'], p['metric'])}"
                f" ({p['pct_used']:.0f}%) · win {p['cycle_start']}→{p['cycle_end']}")
            if p["days_left"] is not None:
                tail = (f" · est. exhaust {p['est_exhaust_date']}"
                        if p["projected_over_cap"] else "")
                lines.append(
                    f"    ~{_fmt(p['remaining'], p['metric'])} left → ~{p['days_left']:.1f} days"
                    f" ({_fmt(p['avg30'], p['metric'])}/day) · {status}{tail}")
    else:
        lines.append("  No caps configured — skipping 'days left'.")
        lines.append(f"  Add caps at {DEFAULT_CAPS_PATH} "
                     "({source: {metric, cap, period}}).")

    total_days = defaultdict(int)
    hourly_total = defaultdict(int)
    for b in burns.values():
        for d, v in b["days"].items():
            total_days[d] += v
        if b["metric"] == METRIC_TOKENS:
            for h, v in b["hourly"].items():
                hourly_total[h] += v

    lines.append("")
    if total_days:
        cutoff = (today_dt - timedelta(days=29)).strftime("%Y-%m-%d")
        recent = [v for d, v in sorted(total_days.items()) if d >= cutoff]
        lines.append(sparkline(recent, label="Daily (30d)"))

    if hourly_total:
        peak = max(hourly_total, key=hourly_total.get)
        lines.append("  Hourly burn (30d, token sources): "
                     f"{_hour_bars(hourly_total)}  "
                     f"peak {peak:02d}:00 ({_fmt(hourly_total[peak], METRIC_TOKENS)})")

    if any(b["today"] > 0 for b in burns.values()):
        lines.append("  Note: TODAY is partial (day not over).")
    undated = sum(b["undated_skipped"] for b in burns.values())
    if undated:
        lines.append(f"  Note: {undated} sessions had no timestamp and were skipped.")

    lines.append("")
    return "\n".join(lines)


def usage_report_json(sessions: list, caps: Optional[dict] = None,
                      now: Optional[float] = None) -> dict:
    """Structured JSON form of the usage report."""
    now = now if now is not None else datetime.now().timestamp()
    burns = compute_source_burns(sessions, now)
    caps = caps if caps is not None else load_caps()
    hourly_total = defaultdict(int)
    for b in burns.values():
        if b["metric"] == METRIC_TOKENS:
            for h, v in b["hourly"].items():
                hourly_total[h] += v
    return {
        "computed_at": datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%S"),
        "sources": burns,
        "caps": caps,
        "projections": project_caps(burns, caps, now),
        "hourly_total": dict(sorted(hourly_total.items())),
    }
