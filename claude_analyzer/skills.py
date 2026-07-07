"""Skills and plugins analyzer for .claude directory."""

import os
import glob
import json
from collections import defaultdict

SKILLS_DIR = os.path.expanduser("~/.claude/skills")
PLUGINS_DIR = os.path.expanduser("~/.claude/plugins")


def _read_file_head(path: str, lines: int = 8) -> str:
    """Read first N lines of a file."""
    try:
        with open(path) as f:
            return "".join(f.readline() for _ in range(lines))
    except Exception:
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
            except Exception:
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
            except Exception:
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
