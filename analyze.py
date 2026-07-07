#!/usr/bin/env python3
"""Claude Code session analysis tool.

Usage:
    python3 analyze.py                    # Full summary report
    python3 analyze.py --projects         # Per-project breakdown
    python3 analyze.py --models           # Model usage details
    python3 analyze.py --tools            # Tool usage breakdown
    python3 analyze.py --sessions         # List top 20 sessions
    python3 analyze.py --sessions 50      # List top 50 sessions
    python3 analyze.py --project evc      # Filter by project
    python3 analyze.py --source projects  # Only projects/ data
    python3 analyze.py --json             # JSON output
    python3 analyze.py --all              # Everything
    python3 analyze.py --timeline         # Time-series with sparklines
    python3 analyze.py --timeline weekly  # Weekly bucketed sparklines
    python3 analyze.py --diff session_a session_b  # Compare two sessions
    python3 analyze.py --diff --project-a evc --project-b ia  # Compare projects
    python3 analyze.py --memory           # Memory file analysis
    python3 analyze.py --memory-inventory # Full memory file listing
    python3 analyze.py --skills           # Skills analysis
    python3 analyze.py --plugins          # Plugins analysis
    python3 analyze.py --search-tool "trello_create_card"  # Search tool calls
    python3 analyze.py --search-card "Order recommendations"  # Find Trello card
    python3 analyze.py --card-context <session_id> <msg_idx>  # Show conversation
"""

import argparse
import json
import sys

from claude_analyzer.parser import parse_sessions, enrich_sessions
from claude_analyzer.stats import compute_stats, format_number, format_tokens
from claude_analyzer.viz import summary, project_detail, session_list


# ═══════════════════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _run_special_reports(args):
    """Handle --memory, --skills, --plugins flags that don't need sessions."""
    ran = False
    if args.memory:
        from claude_analyzer.memory import analyze_memory
        print(analyze_memory())
        ran = True
    if getattr(args, "memory_inventory", False):
        from claude_analyzer.memory import memory_inventory
        print(memory_inventory())
        ran = True
    if args.skills:
        from claude_analyzer.skills import analyze_skills, recommendations
        print(analyze_skills())
        print(recommendations())
        ran = True
    if args.plugins:
        from claude_analyzer.skills import analyze_plugins
        print(analyze_plugins())
        ran = True
    return ran


def _run_search_modes(args, sessions):
    """Handle --search-tool, --search-card, --card-context."""
    from claude_analyzer.search import (
        build_tool_index, search_tool_calls, search_report,
        find_sessions_by_card, card_report, get_conversation_context,
    )

    if args.card_context:
        sid, idx_str = args.card_context
        ctx = get_conversation_context(sessions, sid, int(idx_str))
        if ctx:
            sess = ctx["session"]
            print(f"\n┌─ CONTEXT: [{sess.project}] {sid[:20]}... ─┐")
            print(f"  First msg: {(sess.first_user_msg or '')[:200]}")
            for m in ctx["messages"]:
                marker = " >>>" if m["idx"] == ctx["highlighted_idx"] else "   "
                role_icon = "👤" if m["role"] == "user" else "🤖"
                print(f"{marker} {role_icon} [{m['type']}] {m['text'][:300]}")
                if m["tools"]:
                    print(f"       🛠️  {', '.join(m['tools'][:8])}")
        else:
            print(f"Session {sid} not found.")
        return True

    index = build_tool_index(sessions)
    if args.search_card:
        print(card_report(index, args.search_card))
        return True
    if args.search_tool:
        print(search_report(index, args.search_tool))
        return True
    return False


def _run_diff_mode(args, sessions):
    """Handle --diff flag for comparing sessions or projects."""
    if args.diff is None or len(args.diff) < 2:
        return False
    from claude_analyzer.diff import diff_sessions, diff_projects
    a_id, b_id = args.diff[0], args.diff[1]
    if args.project_a and args.project_b:
        print(diff_projects(sessions, args.project_a, args.project_b))
    else:
        sess_a = next((s for s in sessions if s.session_id.startswith(a_id)), None)
        sess_b = next((s for s in sessions if s.session_id.startswith(b_id)), None)
        if sess_a and sess_b:
            print(diff_sessions(sess_a, sess_b))
        else:
            print(diff_projects(sessions, a_id, b_id))
    return True


def _run_timeline_mode(args, sessions):
    """Handle --timeline flag for sparkline output."""
    if args.timeline is None:
        return False
    from claude_analyzer.timeline import timeline_report
    print(timeline_report(sessions, bucket=args.timeline))
    return True


def _output_json(stats):
    """Output stats as JSON."""
    output = {
        "total_sessions": stats.total_sessions,
        "total_messages": stats.total_messages,
        "total_lines": stats.total_lines,
        "total_size_mb": round(stats.total_size_mb, 1),
        "input_tokens": stats.total_input_tokens,
        "output_tokens": stats.total_output_tokens,
        "cache_read_tokens": stats.total_cache_read,
        "cache_create_tokens": stats.total_cache_create,
        "cache_hit_ratio": round(stats.cache_hit_ratio, 1),
        "estimated_cost_usd": round(stats.estimated_cost, 2),
        "models": dict(stats.model_counts.most_common()),
        "tools": dict(stats.tool_counts.most_common(20)),
        "projects": dict(stats.projects.most_common()),
        "project_tokens": {
            k: v for k, v in
            sorted(stats.project_tokens.items(), key=lambda x: x[1], reverse=True)[:20]
        },
        "project_size_mb": {
            k: round(v / (1024 * 1024), 1)
            for k, v in
            sorted(stats.project_size.items(), key=lambda x: x[1], reverse=True)[:20]
        },
        "session_lengths": {
            "min": min(stats.session_lengths) if stats.session_lengths else 0,
            "max": max(stats.session_lengths) if stats.session_lengths else 0,
            "median": (
                sorted(stats.session_lengths)[len(stats.session_lengths) // 2]
                if stats.session_lengths else 0
            ),
            "average": (
                sum(stats.session_lengths) // len(stats.session_lengths)
                if stats.session_lengths else 0
            ),
        },
    }
    print(json.dumps(output, indent=2))


def _output_text_reports(args, stats, sessions):
    """Output text-based reports for summary, projects, models, tools, sessions."""
    if args.all or (not any([args.projects, args.models, args.tools,
                             args.sessions is not None])):
        print(summary(stats))
    if args.projects or args.all:
        print(project_detail(stats, args.project))
    if args.models or args.all:
        print("\n┌─ MODEL DETAILS ────────────────────────────────┐")
        for model, count in stats.model_counts.most_common(15):
            inp = stats.model_input_tokens.get(model, 0)
            out = stats.model_output_tokens.get(model, 0)
            print(f"  {model}")
            print(f"    Calls: {format_number(count)}  |  "
                  f"In: {format_tokens(inp)}  |  Out: {format_tokens(out)}")
    if args.tools or args.all:
        print("\n┌─ TOOL USAGE DETAILS ───────────────────────────┐")
        max_val = max(stats.tool_counts.values()) if stats.tool_counts else 1
        for tool, count in stats.tool_counts.most_common(25):
            bar_len = int(count / max_val * 40) if max_val > 0 else 0
            print(f"  {tool:<30} {format_number(count):>10} {'█' * bar_len}")
    if args.sessions is not None or args.all:
        limit = args.sessions if args.sessions is not None else 20
        print(session_list(sessions, limit))


# ═══════════════════════════════════════════════════════════════════════════════
# Argument parser
# ═══════════════════════════════════════════════════════════════════════════════

def _build_parser():
    parser = argparse.ArgumentParser(
        description="Analyze Claude Code session history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", choices=["all", "claude", "freebuff", "mimo", "opencode", "antigravity"],
                        default="all", help="Which session source to analyze")
    parser.add_argument("--project", type=str, help="Filter to project (substring match)")
    parser.add_argument("--projects", action="store_true", help="Per-project breakdown")
    parser.add_argument("--models", action="store_true", help="Detailed model usage")
    parser.add_argument("--tools", action="store_true", help="Tool usage breakdown")
    parser.add_argument("--sessions", nargs="?", const=20, type=int, help="List sessions")
    parser.add_argument("--all", action="store_true", help="Show all reports")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--timeline", nargs="?", const="daily",
                        choices=["daily", "weekly", "monthly"], help="Time-series sparklines")
    parser.add_argument("--diff", nargs="*", metavar=("A", "B"), help="Compare sessions/projects")
    parser.add_argument("--project-a", type=str, help="First project for --diff")
    parser.add_argument("--project-b", type=str, help="Second project for --diff")
    parser.add_argument("--memory", action="store_true", help="Memory file analysis")
    parser.add_argument("--memory-inventory", action="store_true", help="Full memory inventory")
    parser.add_argument("--skills", action="store_true", help="Skills analysis")
    parser.add_argument("--plugins", action="store_true", help="Plugins analysis")
    parser.add_argument("--search-tool", type=str, metavar="QUERY", help="Search tool calls")
    parser.add_argument("--search-card", type=str, metavar="CARD_NAME", help="Find Trello card")
    parser.add_argument("--card-context", nargs=2, metavar=("SESSION_ID", "MSG_IDX"),
                        help="Show conversation context")
    return parser


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = _build_parser()
    args = parser.parse_args()

    any_special = args.memory or getattr(args, "memory_inventory", False) or \
                  args.skills or args.plugins
    ran_special = _run_special_reports(args) if any_special else False

    any_session_flags = any([args.projects, args.models, args.tools,
                             args.sessions is not None, args.all,
                             args.timeline is not None, args.diff is not None, args.json])
    if ran_special and not any_session_flags:
        return

    any_search = args.search_tool or args.search_card or args.card_context
    needs_sessions = any_search or any_session_flags

    if not needs_sessions:
        parser.print_help()
        return

    print("Parsing session data...", file=sys.stderr)
    sessions = parse_sessions(source=args.source)
    enrich_sessions(sessions)
    print(f"Found {len(sessions)} sessions", file=sys.stderr)

    if args.project:
        sessions = [s for s in sessions if args.project.lower() in s.project.lower()]
        print(f"Filtered to {len(sessions)} matching '{args.project}'", file=sys.stderr)

    if any_search and _run_search_modes(args, sessions):
        return

    stats = compute_stats(sessions)

    if _run_diff_mode(args, sessions) and not args.all:
        return
    if _run_timeline_mode(args, sessions) and not args.all:
        return

    if args.json:
        _output_json(stats)
        return

    _output_text_reports(args, stats, sessions)


if __name__ == "__main__":
    main()
