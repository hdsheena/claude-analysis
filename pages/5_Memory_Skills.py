"""Page: Memory & Skills - Memory files, skills, plugins, and repo config analysis."""

import streamlit as st

st.set_page_config(
    page_title="Memory & Skills - Claude Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

import os
import glob
import json
import pandas as pd
import plotly.express as px
from collections import defaultdict

from claude_analyzer.memory import collect_memory_file_data
from claude_analyzer.skills import scan_repo_tool_dirs, categorize_repo_files, TOOL_CONFIG_DIRS
from shared import render_sidebar


# ═══════════════════════════════════════════════════════════════════════════════
# Tab render functions
# ═══════════════════════════════════════════════════════════════════════════════

def _render_memory_tab():
    """Scan and display memory files across projects."""
    st.subheader("📝 Memory File Analysis")

    file_data = collect_memory_file_data()

    if not file_data:
        st.info("No memory files found.")
        return

    # Remap to TitleCase keys for Pandas display
    df_mem = pd.DataFrame([{
        "Name": d["name"], "Project": d["project"],
        "Category": d["category"], "Size": d["size"],
        "Hash": d["hash"], "Header": d["header"], "Path": d["path"],
    } for d in file_data])
    unique_hashes = df_mem["Hash"].nunique()
    dup_count = len(df_mem) - unique_hashes

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total Files", len(df_mem))
    with c2: st.metric("Unique (by content)", unique_hashes)
    with c3: st.metric("Duplicates", dup_count)
    with c4:
        total_bytes = df_mem["Size"].sum()
        st.metric("Total Size", f"{total_bytes:,} bytes")

    st.subheader("By Category")
    cats = df_mem["Category"].value_counts()
    df_cats = pd.DataFrame({
        "Category": cats.index, "Count": cats.values,
        "Size": [df_mem[df_mem["Category"] == cat]["Size"].sum() for cat in cats.index],
    })

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.pie(df_cats, names="Category", values="Count", hole=0.4)
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0),
                          paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        proj_counts = df_mem["Project"].value_counts().head(15)
        df_proj_mem = pd.DataFrame({"Project": proj_counts.index, "Files": proj_counts.values})
        fig = px.bar(df_proj_mem, x="Files", y="Project", orientation="h",
                     color_discrete_sequence=["#636efa"])
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("📋 Full Inventory")
    st.dataframe(
        df_mem[["Name", "Project", "Category", "Size", "Header"]],
        use_container_width=True, hide_index=True,
        column_config={
            "Name": st.column_config.TextColumn("File"),
            "Project": st.column_config.TextColumn("Project"),
            "Category": st.column_config.TextColumn("Category"),
            "Size": st.column_config.NumberColumn("Size (bytes)", format=","),
            "Header": st.column_config.TextColumn("First Line", width="large"),
        },
    )

    if dup_count > 0:
        st.divider()
        st.subheader("🔁 Duplicate Files (identical content)")
        hash_groups = defaultdict(list)
        for _, row in df_mem.iterrows():
            hash_groups[row["Hash"]].append(row)
        for h, group in hash_groups.items():
            if len(group) > 1:
                names = ", ".join(f"{r['Project']}/{r['Name']}" for r in group)
                st.caption(f"**{group[0]['Name']}** — {len(group)} copies: {names}")


def _render_skills_tab():
    """Display installed skills from ~/.claude/skills."""
    st.subheader("🔧 Installed Skills")
    skills_dir = os.path.expanduser("~/.claude/skills")

    if not os.path.isdir(skills_dir):
        st.info("No skills directory found at ~/.claude/skills")
        return

    items = os.listdir(skills_dir)
    skill_data = []
    for item in sorted(items):
        full = os.path.join(skills_dir, item)
        is_symlink = os.path.islink(full)
        is_dir = os.path.isdir(full) and not is_symlink
        is_file = os.path.isfile(full) and not is_symlink

        entry = {"Name": item, "Type": "directory" if is_dir else "file",
                 "Symlink": is_symlink, "Size": 0, "Preview": ""}
        if is_file and item.endswith(".md"):
            entry["Size"] = os.path.getsize(full)
            try:
                with open(full) as f:
                    content = "".join(f.readline() for _ in range(15))
                entry["Preview"] = content[:300]
                for line in content.split("\n"):
                    if "description" in line.lower() or "when" in line.lower():
                        entry["Preview"] = line.strip()[:120]
                        break
            except Exception:
                entry["Preview"] = "(unreadable)"
        if is_symlink:
            try:
                entry["Target"] = os.readlink(full)[:80]
            except Exception:
                entry["Target"] = "?"

        skill_data.append(entry)

    df_skills = pd.DataFrame(skill_data)
    custom = [s for s in skill_data if s["Type"] == "file" and not s["Symlink"]]
    symlinked = [s for s in skill_data if s["Symlink"]]
    dirs = [s for s in skill_data if s["Type"] == "directory" and not s["Symlink"]]

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total Entries", len(skill_data))
    with c2: st.metric("Custom Skills", len(custom))
    with c3: st.metric("Symlinked (built-in)", len(symlinked))
    with c4: st.metric("Subdirectories", len(dirs))

    if custom:
        st.subheader("📝 Custom Skills")
        st.dataframe(
            pd.DataFrame(custom)[["Name", "Size", "Preview"]],
            use_container_width=True, hide_index=True,
            column_config={
                "Name": st.column_config.TextColumn("File"),
                "Size": st.column_config.NumberColumn("Size (bytes)", format=","),
                "Preview": st.column_config.TextColumn("Description", width="large"),
            },
        )
    if symlinked:
        st.subheader("🔗 Built-in Skills (symlinks)")
        st.dataframe(
            pd.DataFrame(symlinked)[["Name", "Target"]],
            use_container_width=True, hide_index=True,
            column_config={
                "Name": st.column_config.TextColumn("Skill"),
                "Target": st.column_config.TextColumn("Target Path", width="large"),
            },
        )
    if dirs:
        st.subheader("📁 Skill Directories")
        for d in dirs:
            sub_path = os.path.join(skills_dir, d["Name"])
            sub_items = os.listdir(sub_path) if os.path.isdir(sub_path) else []
            st.caption(f"**{d['Name']}/** — {len(sub_items)} items")


def _render_plugins_tab():
    """Display installed plugins and marketplaces from ~/.claude/plugins."""
    st.subheader("🔌 Installed Plugins & Marketplaces")
    plugins_dir = os.path.expanduser("~/.claude/plugins")

    if not os.path.isdir(plugins_dir):
        st.info("No plugins directory found at ~/.claude/plugins")
        return

    st.caption("**Configuration files:**")
    for cfg in ["known_marketplaces.json", "blocklist.json"]:
        path = os.path.join(plugins_dir, cfg)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    st.caption(f"  • **{cfg}**: {len(data)} entries")
                elif isinstance(data, dict):
                    st.caption(f"  • **{cfg}**: {len(data)} keys")
            except Exception:
                st.caption(f"  • **{cfg}**: (parse error)")

    marketplaces_dir = os.path.join(plugins_dir, "marketplaces")
    if os.path.isdir(marketplaces_dir):
        st.divider()
        st.subheader("🏪 Marketplaces")
        for mp in sorted(os.listdir(marketplaces_dir)):
            mp_path = os.path.join(marketplaces_dir, mp)
            if os.path.isdir(mp_path):
                plugins_path = os.path.join(mp_path, "plugins")
                external_path = os.path.join(mp_path, "external_plugins")
                plugin_count = len(os.listdir(plugins_path)) if os.path.isdir(plugins_path) else 0
                ext_count = len(os.listdir(external_path)) if os.path.isdir(external_path) else 0
                with st.expander(
                    f"**{mp}** — {plugin_count} plugins, {ext_count} external",
                    expanded=plugin_count + ext_count < 20,
                ):
                    if os.path.isdir(plugins_path):
                        st.caption("Plugins:")
                        for plugin in sorted(os.listdir(plugins_path))[:10]:
                            st.caption(f"  • {plugin}")
                        if plugin_count > 10:
                            st.caption(f"  ... and {plugin_count - 10} more")
                    if os.path.isdir(external_path) and ext_count > 0:
                        st.caption("External:")
                        for plugin in sorted(os.listdir(external_path))[:5]:
                            st.caption(f"  • {plugin}")
                        if ext_count > 5:
                            st.caption(f"  ... and {ext_count - 5} more")

    manifests = glob.glob(os.path.join(plugins_dir, "**", "manifest.json"), recursive=True)
    manifests = [m for m in manifests if "marketplaces" not in m]
    if manifests:
        st.divider()
        st.subheader("📦 Installed Plugin Manifests")
        manifest_data = []
        for m in manifests[:20]:
            rel = m.replace(plugins_dir, "").lstrip("/")
            try:
                with open(m) as f:
                    d = json.load(f)
                manifest_data.append({"Name": d.get("name", "?"), "Version": d.get("version", "?"), "Path": rel})
            except Exception:
                manifest_data.append({"Name": "?", "Version": "?", "Path": rel})
        st.dataframe(pd.DataFrame(manifest_data), use_container_width=True, hide_index=True)
    else:
        st.caption("No installed plugin manifests found.")


def _render_data_sources_tab():
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

    @st.cache_data(ttl=86400, show_spinner="Counting sessions...")
    def _count_sessions_by_source():
        counts = {}
        for d in [os.path.expanduser("~/.claude/projects"),
                  os.path.expanduser("~/Library/Application Support/Claude/local-agent-mode-sessions")]:
            if os.path.isdir(d):
                key = "projects" if "projects" in d else "local-agent"
                counts[key] = len(glob.glob(os.path.join(d, "**", "*.jsonl"), recursive=True))
        fb = os.path.expanduser("~/.config/manicode/projects")
        if os.path.isdir(fb):
            counts["freebuff"] = len(glob.glob(os.path.join(fb, "*", "chats", "*", "chat-messages.json")))
        import sqlite3
        for db_path, key in [(os.path.expanduser("~/.local/share/mimocode/mimocode.db"), "mimo"),
                             (os.path.expanduser("~/.local/share/opencode/opencode.db"), "opencode")]:
            if os.path.isfile(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    row = conn.execute("SELECT COUNT(*) FROM session").fetchone()
                    counts[key] = row[0] if row else 0
                    conn.close()
                except Exception:
                    counts[key] = "?"
        brain_dir = os.path.expanduser("~/.gemini/antigravity/brain")
        if os.path.isdir(brain_dir):
            counts["antigravity"] = len(glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl")))
        return counts

    try:
        counts = _count_sessions_by_source()
        cols = st.columns(5)
        sources_order = ["claude", "freebuff", "mimo", "opencode", "antigravity"]
        for i, src_key in enumerate(sources_order):
            with cols[i]:
                val = counts.get(src_key, 0)
                if src_key == "claude":
                    val = counts.get("projects", 0) + counts.get("local-agent", 0)
                st.metric(src_key.replace("-", " ").title(), val)
    except Exception:
        st.caption("(Could not count sessions)")


# categorize_repo_files and scan_repo_tool_dirs are now in claude_analyzer.skills



# categorize_repo_files and scan_repo_tool_dirs are in claude_analyzer.skills


def _display_repo_files(tool_contents: dict, repo_dirs: list):
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
                except Exception:
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


def _render_repo_configs_tab():
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

    TOOL_DISPLAY = {
        ".claude": {"emoji": "🧠", "label": "Claude Code"},
        ".mimocode": {"emoji": "🤖", "label": "Mimo"},
        ".commandcode": {"emoji": "⌨️", "label": "CommandCode"},
        ".opencode": {"emoji": "🔓", "label": "OpenCode"},
    }

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


# ═══════════════════════════════════════════════════════════════════════════════
# Page entry point
# ═══════════════════════════════════════════════════════════════════════════════

st.title("📝 Memory, Skills & Plugins")

_, _, _ = render_sidebar()

tab_memory, tab_skills, tab_plugins, tab_repo, tab_sources = st.tabs(
    ["📝 Memory Files", "🔧 Skills", "🔌 Plugins", "🗂️ Repo Configs", "📂 Data Sources"]
)

with tab_memory:
    _render_memory_tab()

with tab_skills:
    _render_skills_tab()

with tab_plugins:
    _render_plugins_tab()

with tab_sources:
    _render_data_sources_tab()

with tab_repo:
    _render_repo_configs_tab()
