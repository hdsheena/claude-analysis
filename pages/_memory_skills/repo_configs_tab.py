"""Repo configs tab — scan repos for .claude, .mimocode, .opencode configs."""

import os
from collections import defaultdict
import pandas as pd
import streamlit as st

from claude_analyzer.skills import scan_repo_tool_dirs, categorize_repo_files


TOOL_DISPLAY = {
    ".claude": {"emoji": "🧠", "label": "Claude Code"},
    ".mimocode": {"emoji": "🤖", "label": "Mimo"},
    ".commandcode": {"emoji": "⌨️", "label": "CommandCode"},
    ".opencode": {"emoji": "🔓", "label": "OpenCode"},
}


def _display_repo_files(tool_contents: dict, repo_dirs: list) -> None:
    """Display categorized files table for a tool across repos."""
    all_files = []
    for d in repo_dirs:
        repo_name = os.path.basename(os.path.dirname(d))
        cats = tool_contents[repo_name]
        for cat, files in cats.items():
            if cat == "other":
                continue
            for relpath in files[:5]:
                fpath = os.path.join(d, relpath)
                try:
                    header = open(fpath, encoding="utf-8", errors="replace").readline().strip()
                except (OSError, UnicodeDecodeError):
                    header = "(unreadable)"
                all_files.append({
                    "Repo": repo_name, "Category": cat,
                    "File": relpath, "Header": header[:120],
                })

    repo_rows = []
    for repo_name, cats in tool_contents.items():
        row = {"Repo": repo_name}
        for cat in ["skills", "plans", "commands", "settings", "memory",
                    "hooks", "agents", "taste", "config", "other"]:
            count = len(cats.get(cat, []))
            if count > 0:
                row[cat.capitalize()] = count
        repo_rows.append(row)

    total_files = sum(len(v) for cats in tool_contents.values() for v in cats.values())
    st.caption(f"**{total_files} files** across {len(repo_dirs)} repo(s)")
    st.dataframe(pd.DataFrame(repo_rows), use_container_width=True, hide_index=True)

    if all_files:
        by_cat = defaultdict(list)
        for f in all_files:
            by_cat[f["Category"]].append(f)
        for cat in ["skills", "plans", "commands", "memory", "taste",
                    "settings", "hooks", "agents", "config"]:
            items = by_cat.get(cat, [])
            if items:
                st.caption(f"**{cat.capitalize()}** ({len(items)} files)")
                st.dataframe(
                    pd.DataFrame(items)[["Repo", "File", "Header"]],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Repo": st.column_config.TextColumn("Repo", width="small"),
                        "File": st.column_config.TextColumn("File"),
                        "Header": st.column_config.TextColumn("Header", width="large"),
                    },
                )


def render() -> None:
    """Scan repos for .claude, .mimocode, .opencode, .commandcode configs."""
    st.subheader("🗂️ Repo-Level Tool Configurations")
    st.caption("Scans repos for per-project configuration from Claude Code, Mimo, CommandCode, and OpenCode.")

    @st.cache_data(ttl=86400, show_spinner="Scanning repo configs...")
    def _cached_scan():
        return scan_repo_tool_dirs()

    all_tool_dirs = _cached_scan()
    total_dirs = sum(len(v) for v in all_tool_dirs.values())

    if total_dirs == 0:
        st.info("No repo-level tool configuration directories found.")
        return

    cols = st.columns(len(TOOL_DISPLAY))
    for i, (tool_dir_name, tool_info) in enumerate(TOOL_DISPLAY.items()):
        with cols[i]:
            st.metric(f"{tool_info['emoji']} {tool_info['label']}", f"{len(all_tool_dirs[tool_dir_name])} repos")

    st.divider()

    for tool_dir_name, tool_info in TOOL_DISPLAY.items():
        dirs = all_tool_dirs[tool_dir_name]
        if not dirs:
            continue

        with st.expander(f"{tool_info['emoji']} **{tool_info['label']}** — {len(dirs)} repo(s)",
                         expanded=len(dirs) <= 4):
            tool_contents = {}
            for d in dirs:
                repo_name = os.path.basename(os.path.dirname(d))
                tool_contents[repo_name] = categorize_repo_files(d)
            _display_repo_files(tool_contents, dirs)
