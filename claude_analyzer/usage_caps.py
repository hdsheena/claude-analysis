import calendar
import json
import math
import os
from datetime import date, datetime, timedelta
from typing import Optional

DEFAULT_CAPS_PATH = os.path.expanduser("~/.config/claude-analysis/caps.json")


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
