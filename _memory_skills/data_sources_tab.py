"""Data sources tab — show all directories scanned for session data."""

import os
import glob
import sqlite3
import streamlit as st


@st.cache_data(ttl=86400, show_spinner="Counting sessions...")
def count_sessions_by_source() -> dict:
    """Count session files across all data sources."""
    counts = {}
    for d in [os.path.expanduser("~/.claude/projects"),
              os.path.expanduser("~/Library/Application Support/Claude/local-agent-mode-sessions")]:
        if os.path.isdir(d):
            key = "projects" if "projects" in d else "local-agent"
            counts[key] = len(glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True))
    fb = os.path.expanduser("~/.config/manicode/projects")
    if os.path.isdir(fb):
        counts["freebuff"] = len(glob.glob(os.path.join(fb, "*", "chats", "*", "chat-messages.json")))
    for db_path, key in [(os.path.expanduser("~/.local/share/mimocode/mimocode.db"), "mimo"),
                         (os.path.expanduser("~/.local/share/opencode/opencode.db"), "opencode")]:
        if os.path.isfile(db_path):
            try:
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT COUNT(*) FROM session").fetchone()
                counts[key] = row[0] if row else 0
                conn.close()
            except (sqlite3.Error, OSError):
                counts[key] = "?"
    brain_dir = os.path.expanduser("~/.gemini/antigravity/brain")
    if os.path.isdir(brain_dir):
        counts["antigravity"] = len(glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl")))
    return counts


def render() -> None:
    """Show all data source directories and quick session counts."""
    st.subheader("📂 Data Sources")
    st.caption("All directories and files the app scans for session data.")

    SOURCES = [
        {"name": "Claude Code", "source_key": "claude",
         "paths": [os.path.expanduser("~/.claude/projects"),
                   os.path.expanduser("~/Library/Application Support/Claude/local-agent-mode-sessions")],
         "type": "JSONL files", "pattern": "**/*.jsonl"},
        {"name": "Freebuff / Codebuff", "source_key": "freebuff",
         "paths": [os.path.expanduser("~/.config/manicode/projects")],
         "type": "JSON files", "pattern": "*/chats/*/chat-messages.json"},
        {"name": "Mimo", "source_key": "mimo",
         "paths": [os.path.expanduser("~/.local/share/mimocode/mimocode.db")],
         "type": "SQLite database", "pattern": None},
        {"name": "Opencode", "source_key": "opencode",
         "paths": [os.path.expanduser("~/.local/share/opencode/opencode.db")],
         "type": "SQLite database", "pattern": None},
        {"name": "Antigravity", "source_key": "antigravity",
         "paths": [os.path.expanduser("~/.gemini/antigravity/brain")],
         "type": "transcript.jsonl files", "pattern": ".system_generated/logs/transcript.jsonl"},
    ]

    for src in SOURCES:
        all_paths = []
        file_count = 0
        status = "✅"
        for p in src["paths"]:
            if os.path.exists(p):
                all_paths.append(p)
                if src["pattern"]:
                    files = glob.glob(os.path.join(p, src["pattern"]), recursive=True)
                    file_count += len(files)
                else:
                    try:
                        file_count = os.path.getsize(p)
                    except OSError:
                        pass
            else:
                status = "⚠️ missing"
                all_paths.append(f"{p} (not found)")

        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 5])
            with c1:
                st.caption(f"### {status} {src['name']}")
                st.caption(f"{src['type']} · {file_count} entries")
            with c3:
                for pl in all_paths:
                    st.code(pl, language=None)

    st.divider()

    try:
        counts = count_sessions_by_source()
        cols = st.columns(5)
        sources_order = ["claude", "freebuff", "mimo", "opencode", "antigravity"]
        for i, src_key in enumerate(sources_order):
            with cols[i]:
                val = counts.get(src_key, 0)
                if src_key == "claude":
                    val = counts.get("projects", 0) + counts.get("local-agent", 0)
                st.metric(src_key.replace("-", " ").title(), val)
    except (OSError, KeyError):
        st.caption("(Could not count sessions)")
