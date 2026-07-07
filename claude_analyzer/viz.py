"""Terminal visualizations for Claude session statistics."""

import os
from collections import Counter

from .stats import AggStats, format_number, format_tokens, format_bytes

# --- ASCII bar chart helper ---

try:
    TERM_WIDTH = os.get_terminal_size().columns
except (OSError, ValueError):
    TERM_WIDTH = 80
MAX_BAR = min(TERM_WIDTH - 40, 60)


def _bar_chart(
    data: list,  # list of (label, value) tuples
    title: str,
    max_items: int = 15,
    value_formatter: callable = format_number,
) -> str:
    """Render a horizontal ASCII bar chart."""
    items = data[:max_items]
    max_val = max(v for _, v in items) if items else 1

    lines = [f"\n  {title}", "  " + "─" * 60]

    for label, val in items:
        bar_len = int(val / max_val * MAX_BAR) if max_val > 0 else 0
        bar = "█" * bar_len
        lines.append(f"  {label:<25} {value_formatter(val):>10} {bar}")

    return "\n".join(lines)


def summary(stats: AggStats) -> str:
    """Print a comprehensive summary of all stats."""
    sections = []

    # Header
    sections.append("""
╔══════════════════════════════════════════════════╗
║     CLAUDE CODE SESSION ANALYSIS REPORT          ║
╚══════════════════════════════════════════════════╝""")

    # Overview
    sections.append(f"""
┌─ OVERVIEW ──────────────────────────────────────┐
│ Total sessions:      {stats.total_sessions:>5}                         │
│   from projects/:    {stats.projects_source_count:>5}                         │
│   from local-agent:  {stats.local_agent_count:>5}                         │
│ Total messages:      {format_number(stats.total_messages):>10}                         │
│ Total lines:         {format_number(stats.total_lines):>10}                         │
│ Total size on disk:  {stats.total_size_mb:>10.0f} MB                      │
└──────────────────────────────────────────────────┘""")

    # Token summary
    total_all_tokens = stats.total_input_tokens + stats.total_output_tokens
    sections.append(f"""
┌─ TOKENS ────────────────────────────────────────┐
│ Input tokens:       {format_tokens(stats.total_input_tokens):>10}                         │
│ Output tokens:      {format_tokens(stats.total_output_tokens):>10}                         │
│ Total I/O:          {format_tokens(total_all_tokens):>10}                         │
│ Cache read:         {format_tokens(stats.total_cache_read):>10}                         │
│ Cache created:      {format_tokens(stats.total_cache_create):>10}                         │
│ Cache hit ratio:    {stats.cache_hit_ratio:>9.1f}%                        │
│ Estimated cost:    ${stats.estimated_cost:>9.2f}                         │
└──────────────────────────────────────────────────┘""")

    # Model distribution
    model_items = [(m, c) for m, c in stats.model_counts.most_common(10)]
    sections.append(_bar_chart(model_items, "MODEL USAGE (assistant calls)"))

    # Also show model token breakdown
    sections.append("\n  Model Token Breakdown:")
    sections.append(f"  {'Model':<30} {'Input':>10} {'Output':>10}")
    sections.append("  " + "─" * 52)
    for model in stats.model_counts.most_common(8):
        m = model[0]
        inp = format_tokens(stats.model_input_tokens.get(m, 0))
        out = format_tokens(stats.model_output_tokens.get(m, 0))
        short_m = m[:28]
        sections.append(f"  {short_m:<30} {inp:>10} {out:>10}")

    # Project breakdown
    project_items = [(p, c) for p, c in stats.projects.most_common(15)]
    sections.append(_bar_chart(project_items, "PROJECTS BY SESSION COUNT"))

    # Projects by size
    size_items = sorted(stats.project_size.items(), key=lambda x: x[1], reverse=True)[:15]
    size_chart = _bar_chart(
        [(p, s) for p, s in size_items],
        "PROJECTS BY DISK SIZE",
        value_formatter=format_bytes,
    )
    sections.append(size_chart)

    # Top tools
    tool_items = stats.tool_counts.most_common(15)
    sections.append(_bar_chart(tool_items, "TOP TOOLS USED"))

    # Stop reasons
    stop_items = stats.stop_reasons.most_common(8)
    sections.append(_bar_chart(stop_items, "STOP REASONS"))

    # Message types
    type_items = stats.msg_types.most_common(10)
    sections.append(_bar_chart(type_items, "MESSAGE TYPES"))

    # Session length distribution
    lengths = sorted(stats.session_lengths)
    if lengths:
        sections.append(f"""
  SESSION LENGTH DISTRIBUTION
  {'─' * 60}
  Min: {lengths[0]},  Max: {lengths[-1]},  Median: {lengths[len(lengths)//2]}
  Average: {sum(lengths)//len(lengths)}""")

        # Buckets
        buckets = [
            (0, 10), (10, 25), (25, 50), (50, 100),
            (100, 250), (250, 500), (500, 1000), (1000, 5000),
            (5000, 99999),
        ]
        max_count = 0
        bucket_counts = []
        for lo, hi in buckets:
            count = sum(1 for s in lengths if lo <= s < hi)
            bucket_counts.append((f"{lo:>5}-{hi:<5}", count))
            max_count = max(max_count, count)

        if max_count > 0:
            for label, count in bucket_counts:
                bar_len = int(count / max_count * 40) if max_count > 0 else 0
                bar = "█" * bar_len
                sections.append(f"  {label}: {count:>4} {bar}")

    return "\n".join(sections)


def project_detail(stats: AggStats, project_filter: str = None) -> str:
    """Show detailed breakdown for a specific project or all projects."""
    lines = []
    lines.append("\n┌─ PROJECT DETAILS ──────────────────────────────┐")

    projects_to_show = stats.projects.most_common(20)
    if project_filter:
        projects_to_show = [
            (p, c) for p, c in stats.projects.most_common()
            if project_filter.lower() in p.lower()
        ]

    for proj, session_count in projects_to_show:
        tokens = stats.project_tokens.get(proj, 0)
        size = stats.project_size.get(proj, 0)
        models = stats.project_models.get(proj, {})
        top_model = max(models.items(), key=lambda x: x[1]) if models else ("?", 0)

        lines.append(f"\n  {proj}")
        lines.append(f"    Sessions: {session_count}  |  Tokens: {format_tokens(tokens)}  |  Size: {format_bytes(size)}")
        lines.append(f"    Top model: {top_model[0][:40]} ({top_model[1]} calls)")

    return "\n".join(lines)


def session_list(sessions: list, limit: int = 20) -> str:
    """Show a list of sessions with key stats."""
    lines = []
    lines.append(f"\n┌─ SESSION LIST (showing {min(limit, len(sessions))} of {len(sessions)}) {'─' * 20}┐")
    lines.append(f"  {'ID':<10} {'Project':<25} {'Msgs':>6} {'Tokens':>10} {'First msg...'}")
    lines.append("  " + "─" * 90)

    # Sort by message count desc
    sorted_sessions = sorted(sessions, key=lambda s: len(s.messages), reverse=True)

    for sess in sorted_sessions[:limit]:
        sid = sess.session_id[:8]
        proj = sess.project[:23]
        msgs = len(sess.messages)
        tokens = format_tokens(sess.total_input_tokens + sess.total_output_tokens)
        first = (sess.first_user_msg or "")[:35].replace("\n", " ")
        lines.append(f"  {sid:<10} {proj:<25} {msgs:>6} {tokens:>10} {first}")

    return "\n".join(lines)
