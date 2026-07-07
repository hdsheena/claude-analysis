#!/usr/bin/env python3
"""Claude Code session analysis tool.

Usage:
    python3 analyze.py              # Full summary report
    python3 analyze.py --projects   # Per-project breakdown
    python3 analyze.py --models     # Model usage details
    python3 analyze.py --tools      # Tool usage breakdown
    python3 analyze.py --sessions   # List top 20 sessions
    python3 analyze.py --sessions 50  # List top 50 sessions
    python3 analyze.py --project inventory  # Filter by project
    python3 analyze.py --source projects    # Only projects/ data
    python3 analyze.py --json              # JSON output
    python3 analyze.py --all               # Everything
"""

import argparse
import json
import sys

from claude_analyzer.parser import parse_sessions, enrich_sessions
from claude_analyzer.stats import compute_stats, format_number, format_tokens
from claude_analyzer.viz import summary, project_detail, session_list


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Claude Code session history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=["all", "projects", "local-agent"],
        default="all",
        help="Which session source to analyze (default: all)",
    )
    parser.add_argument(
        "--project",
        type=str,
        help="Filter results to a specific project (substring match)",
    )
    parser.add_argument(
        "--projects",
        action="store_true",
        help="Show per-project breakdown",
    )
    parser.add_argument(
        "--models",
        action="store_true",
        help="Show detailed model usage",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="Show tool usage breakdown",
    )
    parser.add_argument(
        "--sessions",
        nargs="?",
        const=20,
        type=int,
        help="List sessions (default: 20, or specify count)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all reports",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of text",
    )

    args = parser.parse_args()

    # If no flags given, default to summary
    show_summary = not any([
        args.projects, args.models, args.tools,
        args.sessions is not None, args.all,
    ]) or args.all
    show_projects = args.projects or args.all
    show_models = args.models or args.all
    show_tools = args.tools or args.all
    show_sessions = args.sessions is not None or args.all
    session_limit = args.sessions if args.sessions is not None else 20

    # Parse all sessions
    print("Parsing session data...", file=sys.stderr)
    sessions = parse_sessions(source=args.source)
    enrich_sessions(sessions)
    print(f"Found {len(sessions)} sessions", file=sys.stderr)

    # Filter by project if requested — recompute stats on filtered set
    if args.project:
        sessions = [
            s for s in sessions
            if args.project.lower() in s.project.lower()
        ]
        print(f"Filtered to {len(sessions)} sessions matching '{args.project}'",
              file=sys.stderr)

    stats = compute_stats(sessions)

    # JSON output
    if args.json:
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
                "median": (sorted(stats.session_lengths)[len(stats.session_lengths)//2]
                           if stats.session_lengths else 0),
                "average": (sum(stats.session_lengths) // len(stats.session_lengths)
                            if stats.session_lengths else 0),
            },
        }
        print(json.dumps(output, indent=2))
        return

    # Text output
    if show_summary:
        print(summary(stats))

    if show_projects:
        print(project_detail(stats, args.project))

    if show_models:
        print("\n┌─ MODEL DETAILS ────────────────────────────────┐")
        for model, count in stats.model_counts.most_common(15):
            inp = stats.model_input_tokens.get(model, 0)
            out = stats.model_output_tokens.get(model, 0)
            print(f"  {model}")
            print(f"    Calls: {format_number(count)}  |  "
                  f"In: {format_tokens(inp)}  |  Out: {format_tokens(out)}")

    if show_tools:
        print("\n┌─ TOOL USAGE DETAILS ───────────────────────────┐")
        max_val = max(stats.tool_counts.values()) if stats.tool_counts else 1
        for tool, count in stats.tool_counts.most_common(25):
            bar_len = int(count / max_val * 40) if max_val > 0 else 0
            print(f"  {tool:<30} {format_number(count):>10} {'█' * bar_len}")

    if show_sessions:
        print(session_list(sessions, session_limit))


if __name__ == "__main__":
    main()
