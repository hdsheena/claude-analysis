"""Skills, plugins, and repo configuration analyzer for .claude directory."""

import os
import glob
import json
import sqlite3
from collections import defaultdict

SKILLS_DIR = os.path.expanduser("~/.claude/skills")
PLUGINS_DIR = os.path.expanduser("~/.claude/plugins")


# ═══════════════════════════════════════════════════════════════════════════════
# Repo-level tool configuration scanning
# Used by both CLI (--skills) and Streamlit (Memory_Skills page)
# ═══════════════════════════════════════════════════════════════════════════════

TOOL_CONFIG_DIRS = {
    ".claude": "Claude Code",
    ".mimocode": "Mimo",
    ".commandcode": "CommandCode",
    ".opencode": "OpenCode",
}


def _opencode_repo_dirs() -> list:
    """Get unique workspace/repo directories from OpenCode SQLite DB."""
    db_path = os.path.expanduser("~/.local/share/opencode/opencode.db")
    if not os.path.isfile(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT directory FROM session WHERE directory IS NOT NULL AND directory != ''"
        ).fetchall()
        conn.close()
        return sorted(set(r[0] for r in rows))
    except sqlite3.Error:
        return []


def _antigravity_repo_dirs() -> list:
    """Get project directories from Antigravity brain."""
    brain_dir = os.path.expanduser("~/.gemini/antigravity/brain")
    if not os.path.isdir(brain_dir):
        return []
    return [os.path.join(brain_dir, d) for d in sorted(os.listdir(brain_dir))
            if os.path.isdir(os.path.join(brain_dir, d))]


def scan_repo_tool_dirs() -> dict:
    """Scan for repos associated with each tool.

    For tools with per-repo config dirs (.claude, .mimocode, .commandcode):
    scans GitHub repos for those directories.

    For tools without config dirs (.opencode, .antigravity): queries their
    data stores for repo/workspace directories that have session data.

    Returns dict keyed by directory/source name with a list of paths.
    """
    from .disk_cache import cache_get, cache_set
    cached = cache_get("repo_tool_dirs")
    if cached is not None:
        return cached
    repo_roots = [
        os.path.expanduser("~/GitHub"),
        os.path.expanduser("~/Documents/GitHub"),
        os.path.expanduser("~/orca/workspaces"),
    ]
    result = {}

    # Tools with per-repo config directories
    for tool_dir_name in [".claude", ".mimocode", ".commandcode"]:
        dirs = []
        for root in repo_roots:
            if not os.path.isdir(root):
                continue
            depth = 2 if "orca" in root else 1
            pattern = os.path.join(root, *(["*"] * depth), tool_dir_name)
            dirs.extend(glob.glob(pattern))
        result[tool_dir_name] = sorted(set(dirs))

    # Tools backed by data stores (no per-repo config dirs)
    result[".opencode"] = _opencode_repo_dirs()
    result[".antigravity"] = _antigravity_repo_dirs()

    cache_set("repo_tool_dirs", result)
    return result


def categorize_repo_files(repo_dir: str) -> dict:
    """Walk a repo's tool config directory and categorize files by type.

    Returns a dict with keys: skills, plans, commands, settings, memory,
    hooks, agents, taste, config, other. Each maps to a list of relative paths.
    """
    categories = {"skills": [], "plans": [], "commands": [], "settings": [],
                  "memory": [], "hooks": [], "agents": [], "taste": [],
                  "config": [], "other": []}

    for walk_root, walk_dirs, walk_files in os.walk(repo_dir):
        walk_dirs[:] = [wd for wd in walk_dirs if wd != "node_modules"]
        rel = os.path.relpath(walk_root, repo_dir)
        for fname in walk_files:
            relpath = os.path.join(rel, fname) if rel != "." else fname
            if "skills" in rel.split(os.sep) or fname.endswith("SKILL.md"):
                categories["skills"].append(relpath)
            elif "plans" in rel.split(os.sep) and fname.endswith(".md"):
                categories["plans"].append(relpath)
            elif "command" in rel.lower() or "commands" in rel.split(os.sep):
                categories["commands"].append(relpath)
            elif fname.endswith(".json") and "setting" in fname.lower():
                categories["settings"].append(relpath)
            elif "memory" in rel.split(os.sep) and fname.endswith(".md"):
                categories["memory"].append(relpath)
            elif "hooks" in rel.split(os.sep):
                categories["hooks"].append(relpath)
            elif "agents" in rel.split(os.sep) or "agent" in rel.split(os.sep):
                categories["agents"].append(relpath)
            elif "taste" in rel.split(os.sep):
                categories["taste"].append(relpath)
            elif fname == "package.json":
                categories["config"].append(relpath)
            else:
                categories["other"].append(relpath)

    return categories


def _read_file_head(path: str, lines: int = 8) -> str:
    """Read first N lines of a file."""
    try:
        with open(path) as f:
            return "".join(f.readline() for _ in range(lines))
    except (OSError, UnicodeDecodeError):
        return "(unreadable)"


def analyze_skills() -> str:
    """Analyze installed skills."""
    if not os.path.isdir(SKILLS_DIR):
        return "\n  No skills directory found."

    items = os.listdir(SKILLS_DIR)
    lines = []
    lines.append("\n┌─ SKILLS ANALYSIS ────────────────────────────────┐")

    skills = []
    for item in sorted(items):
        full = os.path.join(SKILLS_DIR, item)
        is_symlink = os.path.islink(full)
        is_dir = os.path.isdir(full) and not is_symlink
        is_file = os.path.isfile(full) and not is_symlink

        entry = {"name": item, "type": "dir" if is_dir else "file",
                  "symlink": is_symlink, "path": full}

        if is_file and item.endswith(".md"):
            content = _read_file_head(full, 15)
            size = os.path.getsize(full)
            entry["size"] = size
            entry["preview"] = content

            # Extract description/triggers from markdown
            desc = ""
            for line in content.split("\n"):
                if "description" in line.lower() or "when" in line.lower():
                    desc = line.strip()
                    break
            entry["description"] = desc

        if is_symlink:
            target = os.readlink(full)
            entry["target"] = target

        skills.append(entry)

    lines.append(f"  Total entries: {len(skills)}")

    # Custom skill files
    custom = [s for s in skills if s["type"] == "file" and not s["symlink"]]
    symlinked = [s for s in skills if s["symlink"]]
    dirs = [s for s in skills if s["type"] == "dir" and not s["symlink"]]

    lines.append(f"  Custom skills: {len(custom)}")
    lines.append(f"  Symlinked skills: {len(symlinked)}")
    lines.append(f"  Subdirectories: {len(dirs)}")

    if custom:
        lines.append(f"\n  Custom skills:")
        for s in custom:
            lines.append(f"    {s['name']} ({s.get('size', 0)} bytes)")
            if s.get("description"):
                lines.append(f"      {s['description'][:80]}")
            lines.append("")

    if symlinked:
        lines.append(f"  Symlinked (built-in):")
        for s in symlinked:
            lines.append(f"    {s['name']} → {s.get('target', '?')[:60]}")

    if dirs:
        lines.append(f"\n  Subdirectories:")
        for s in dirs:
            subitems = os.listdir(s["path"])
            lines.append(f"    {s['name']}/ ({len(subitems)} items)")

    return "\n".join(lines)


def analyze_plugins() -> str:
    """Analyze installed plugins and marketplaces."""
    if not os.path.isdir(PLUGINS_DIR):
        return "\n  No plugins directory found."

    lines = []
    lines.append("\n┌─ PLUGINS ANALYSIS ───────────────────────────────┐")

    # Root config files
    for cfg in ["known_marketplaces.json", "blocklist.json"]:
        path = os.path.join(PLUGINS_DIR, cfg)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    lines.append(f"  {cfg}: {len(data)} entries")
                    for entry in data[:5]:
                        if isinstance(entry, str):
                            lines.append(f"    • {entry[:70]}")
                        elif isinstance(entry, dict):
                            name = entry.get("name", entry.get("source", "?"))
                            lines.append(f"    • {str(name)[:70]}")
                elif isinstance(data, dict):
                    lines.append(f"  {cfg}: {len(data)} keys")
            except (OSError, json.JSONDecodeError):
                lines.append(f"  {cfg}: (parse error)")

    # Marketplaces
    marketplaces_dir = os.path.join(PLUGINS_DIR, "marketplaces")
    if os.path.isdir(marketplaces_dir):
        lines.append(f"\n  Marketplaces:")
        for mp in sorted(os.listdir(marketplaces_dir)):
            mp_path = os.path.join(marketplaces_dir, mp)
            if os.path.isdir(mp_path):
                # Count plugins in this marketplace
                plugins_path = os.path.join(mp_path, "plugins")
                plugin_count = len(os.listdir(plugins_path)) if os.path.isdir(plugins_path) else 0
                external_path = os.path.join(mp_path, "external_plugins")
                ext_count = len(os.listdir(external_path)) if os.path.isdir(external_path) else 0
                lines.append(f"    {mp}/ — {plugin_count} plugins, {ext_count} external")

                # Show some plugin names
                if os.path.isdir(plugins_path):
                    for plugin in sorted(os.listdir(plugins_path))[:5]:
                        lines.append(f"      • {plugin}")
                    if plugin_count > 5:
                        lines.append(f"      ... and {plugin_count - 5} more")

    # Installed plugin manifests
    manifests = glob.glob(os.path.join(PLUGINS_DIR, "**", "manifest.json"), recursive=True)
    manifests = [m for m in manifests if "marketplaces" not in m]
    if manifests:
        lines.append(f"\n  Installed plugin manifests: {len(manifests)}")
        for m in manifests[:10]:
            rel = m.replace(PLUGINS_DIR, "").lstrip("/")
            try:
                with open(m) as f:
                    d = json.load(f)
                name = d.get("name", "?")
                version = d.get("version", "?")
                lines.append(f"    {name} v{version} ({rel})")
            except (OSError, json.JSONDecodeError):
                lines.append(f"    {rel}")

    return "\n".join(lines)


def recommendations() -> str:
    """Generate recommendations based on skills/plugins analysis."""
    lines = []
    lines.append("\n┌─ RECOMMENDATIONS ────────────────────────────────┐")

    # Check what skills exist
    skill_names = set()
    if os.path.isdir(SKILLS_DIR):
        skill_names = set(
            os.path.splitext(f)[0].replace(".skills", "")
            for f in os.listdir(SKILLS_DIR)
            if f.endswith(".md")
        )
        # Also add symlinks
        for f in os.listdir(SKILLS_DIR):
            full = os.path.join(SKILLS_DIR, f)
            if os.path.islink(full):
                skill_names.add(f)

    lines.append(f"  Skills available: {len(skill_names)}")
    if skill_names:
        lines.append(f"  Names: {', '.join(sorted(skill_names))}")

    # Check if CLAUDE.md references skills
    claude_md = os.path.expanduser("~/.claude/CLAUDE.md")
    has_skill_refs = False
    if os.path.exists(claude_md):
        with open(claude_md) as f:
            claude_content = f.read()
        has_skill_refs = any(
            s in claude_content or f'@skill:{s}' in claude_content or f'@skill-{s}' in claude_content
            for s in skill_names
        )
    if not has_skill_refs and skill_names:
        lines.append(f"\n  ⚠ CLAUDE.md doesn't reference any installed skills.")
        lines.append(f"  Consider adding skill references to CLAUDE.md for automatic loading.")

    # Plugin insights
    plugins_path = os.path.join(PLUGINS_DIR, "marketplaces")
    if os.path.isdir(plugins_path):
        total_plugins = 0
        for mp in os.listdir(plugins_path):
            pp = os.path.join(plugins_path, mp, "plugins")
            if os.path.isdir(pp):
                total_plugins += len(os.listdir(pp))
        lines.append(f"\n  Available plugins from marketplaces: {total_plugins}+")
        lines.append(f"  These can be installed with: npx skills add <owner/repo> --skill <name>")

    # Memory-awareness
    memory_dir = os.path.expanduser("~/.claude/projects")
    memory_files = glob.glob(os.path.join(memory_dir, "**/memory/*.md"), recursive=True)
    if memory_files:
        lines.append(f"\n  Memory files: {len(memory_files)} across projects")
        lines.append(f"  These are automatically loaded as context by Claude Code")

    return "\n".join(lines)
