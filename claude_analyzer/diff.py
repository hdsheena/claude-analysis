"""Side-by-side comparison of sessions or projects."""

from collections import Counter, defaultdict

from .parser import Session
from .stats import format_number, format_tokens, format_bytes


def _session_stats(session: Session) -> dict:
    """Extract key stats from a single session."""
    models = Counter()
    tools = Counter()
    total_input = 0
    total_output = 0
    total_cache = 0
    stop_reasons = Counter()

    for msg in session.messages:
        if msg.msg_type == "assistant":
            if msg.model:
                models[msg.model] += 1
            total_input += msg.input_tokens
            total_output += msg.output_tokens
            total_cache += msg.cache_read_tokens
            stop_reasons[msg.stop_reason or "?"] += 1
            for tool in msg.tools_used:
                tools[tool] += 1

    return {
        "id": session.session_id[:12],
        "project": session.project,
        "messages": len(session.messages),
        "lines": session.line_count,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_read": total_cache,
        "models": dict(models.most_common(5)),
        "tools": dict(tools.most_common(10)),
        "stop_reasons": dict(stop_reasons),
        "first_msg": (session.first_user_msg or "")[:80],
    }


def _aggregate_stats(sessions: list, label: str) -> dict:
    """Aggregate stats across multiple sessions."""
    base = {
        "label": label,
        "sessions": len(sessions),
        "messages": sum(len(s.messages) for s in sessions),
        "lines": sum(s.line_count for s in sessions),
        "input_tokens": sum(s.total_input_tokens for s in sessions),
        "output_tokens": sum(s.total_output_tokens for s in sessions),
        "cache_read": sum(s.total_cache_read for s in sessions),
    }

    models = Counter()
    tools = Counter()
    stop_reasons = Counter()
    for s in sessions:
        for msg in s.messages:
            if msg.msg_type == "assistant":
                if msg.model:
                    models[msg.model] += 1
                stop_reasons[msg.stop_reason or "?"] += 1
                for tool in msg.tools_used:
                    tools[tool] += 1

    base["models"] = dict(models.most_common(8))
    base["tools"] = dict(tools.most_common(10))
    base["stop_reasons"] = dict(stop_reasons)
    return base


def _bar_compare(v1: int, v2: int, width: int = 30) -> str:
    """Render two-side comparison bar."""
    total = v1 + v2
    if total == 0:
        return " " * (width * 2 + 3)
    left_w = max(1, int(v1 / total * width))
    right_w = max(1, int(v2 / total * width))
    return f"{'█' * left_w} │ {'█' * right_w}"


def diff_sessions(s1: Session, s2: Session) -> str:
    """Compare two individual sessions side by side."""
    a = _session_stats(s1)
    b = _session_stats(s2)

    lines = []
    lines.append(f"\n┌─ SESSION DIFF ──────────────────────────────────────────────┐")
    lines.append(f"  {'':<20} {a['id']:<30} {b['id']}")
    lines.append(f"  {'Project':<20} {a['project']:<30} {b['project']}")
    lines.append("  " + "─" * 70)

    rows = [
        ("Messages", a["messages"], b["messages"], format_number),
        ("Lines", a["lines"], b["lines"], format_number),
        ("Input tokens", a["input_tokens"], b["input_tokens"], format_tokens),
        ("Output tokens", a["output_tokens"], b["output_tokens"], format_tokens),
        ("Cache read", a["cache_read"], b["cache_read"], format_tokens),
    ]

    for label, v1, v2, fmt in rows:
        bar = _bar_compare(v1, v2)
        winner = "←" if v1 > v2 else ("→" if v2 > v1 else "=")
        lines.append(f"  {label:<20} {fmt(v1):>10} {fmt(v2):<10} {bar} {winner}")

    # Model comparison
    lines.append("")
    lines.append(f"  {'Models used':<20} {'─' * 50}")
    all_models = set(a["models"]) | set(b["models"])
    for m in sorted(all_models):
        short = m.replace("claude-", "")[:25]
        c1 = a["models"].get(m, 0)
        c2 = b["models"].get(m, 0)
        bar = _bar_compare(c1, c2, 20)
        lines.append(f"  {short:<20} {c1:>5} {c2:<5} {bar}")

    # Tool comparison
    lines.append("")
    lines.append(f"  {'Tools used':<20} {'─' * 50}")
    all_tools = set(a["tools"]) | set(b["tools"])
    for t in sorted(all_tools):
        c1 = a["tools"].get(t, 0)
        c2 = b["tools"].get(t, 0)
        bar = _bar_compare(c1, c2, 20)
        lines.append(f"  {t:<20} {c1:>5} {c2:<5} {bar}")

    # First messages
    lines.append("")
    lines.append(f"  First msg A: {a['first_msg']}")
    lines.append(f"  First msg B: {b['first_msg']}")

    return "\n".join(lines)


def diff_projects(sessions: list, proj_a: str, proj_b: str) -> str:
    """Compare two projects by aggregating their sessions."""
    group_a = [s for s in sessions if proj_a.lower() in s.project.lower()]
    group_b = [s for s in sessions if proj_b.lower() in s.project.lower()]

    if not group_a:
        return f"No sessions found for '{proj_a}'"
    if not group_b:
        return f"No sessions found for '{proj_b}'"

    a = _aggregate_stats(group_a, proj_a)
    b = _aggregate_stats(group_b, proj_b)

    lines = []
    lines.append(f"\n┌─ PROJECT DIFF ──────────────────────────────────────────────┐")
    lines.append(f"  {'':<20} {a['label']:<30} {b['label']}")
    lines.append("  " + "─" * 70)

    rows = [
        ("Sessions", a["sessions"], b["sessions"], format_number),
        ("Messages", a["messages"], b["messages"], format_number),
        ("Lines", a["lines"], b["lines"], format_number),
        ("Input tokens", a["input_tokens"], b["input_tokens"], format_tokens),
        ("Output tokens", a["output_tokens"], b["output_tokens"], format_tokens),
        ("Cache read", a["cache_read"], b["cache_read"], format_tokens),
    ]

    for label, v1, v2, fmt in rows:
        bar = _bar_compare(v1, v2)
        winner = "←" if v1 > v2 else ("→" if v2 > v1 else "=")
        lines.append(f"  {label:<20} {fmt(v1):>10} {fmt(v2):<10} {bar} {winner}")

    # Model comparison
    lines.append("")
    lines.append(f"  {'Models':<20} {'─' * 50}")
    all_models = set(a["models"]) | set(b["models"])
    for m in sorted(all_models):
        short = m.replace("claude-", "")[:25]
        c1 = a["models"].get(m, 0)
        c2 = b["models"].get(m, 0)
        bar = _bar_compare(c1, c2, 20)
        lines.append(f"  {short:<20} {c1:>5} {c2:<5} {bar}")

    # Efficiency metric
    a_eff = a["output_tokens"] / max(a["input_tokens"], 1)
    b_eff = b["output_tokens"] / max(b["input_tokens"], 1)
    lines.append(f"\n  Output/Input ratio: {a_eff:.1f}x vs {b_eff:.1f}x")

    return "\n".join(lines)
