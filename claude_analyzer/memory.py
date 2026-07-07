"""Memory file analyzer for Claude session data."""

import os
import glob
import hashlib
from collections import defaultdict, Counter
from typing import Optional


def _find_memory_files() -> list:
    """Find all memory markdown files in .claude directories."""
    patterns = [
        os.path.expanduser("~/.claude/projects/**/memory/*.md"),
        os.path.expanduser("~/.claude/projects/**/MEMORY.md"),
    ]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern, recursive=True))
    return sorted(set(files))


def _hash_file(filepath: str) -> str:
    """MD5 hash of file contents."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


from .parser import project_name_from_path

def _extract_project(filepath: str) -> str:
    """Extract project name from a memory file path."""
    return project_name_from_path(filepath, "projects")



def _categorize(filename: str) -> str:
    """Categorize a memory file by naming convention."""
    name = filename.lower().replace(".md", "")
    if name.startswith("feedback_"):
        return "feedback"
    if name.startswith("project_"):
        return "project"
    if name.startswith("reference_"):
        return "reference"
    if name == "memory":
        return "index"
    if name in ("stakeholders", "user_identity", "dev_environment"):
        return "meta"
    return "other"


def _read_headers(filepath: str) -> str:
    """Read first line of a memory file."""
    try:
        with open(filepath) as f:
            return f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return "(unreadable)"


def analyze_memory() -> str:
    """Full analysis of all memory files."""
    files = _find_memory_files()

    if not files:
        return "\n  No memory files found."

    # Collect data
    file_data = []
    for fp in files:
        fname = os.path.basename(fp)
        proj = _extract_project(fp)
        cat = _categorize(fname)
        size = os.path.getsize(fp)
        h = _hash_file(fp)
        header = _read_headers(fp)
        file_data.append({
            "path": fp, "name": fname, "project": proj,
            "category": cat, "size": size, "hash": h,
            "header": header,
        })

    # Group by hash to find true duplicates
    hash_groups = defaultdict(list)
    for fd in file_data:
        hash_groups[fd["hash"]].append(fd)

    duplicates = {h: g for h, g in hash_groups.items() if len(g) > 1}
    unique_count = len(hash_groups) - len(duplicates)

    # Group by filename (same name, different content)
    name_groups = defaultdict(list)
    for fd in file_data:
        name_groups[fd["name"]].append(fd)

    same_name_diff_content = {
        n: g for n, g in name_groups.items()
        if len(g) > 1 and len(set(fd["hash"] for fd in g)) > 1
    }

    # Category breakdown
    cats = Counter(fd["category"] for fd in file_data)

    # Project breakdown
    projects = Counter(fd["project"] for fd in file_data)

    # Build report
    lines = []
    lines.append("\n┌─ MEMORY FILE ANALYSIS ───────────────────────────┐")
    lines.append(f"  Total files: {len(file_data)}")
    lines.append(f"  Unique (by content): {unique_count}")
    lines.append(f"  True duplicates: {sum(len(g) - 1 for g in duplicates.values())} redundant files")
    lines.append(f"  Same name, different content: {len(same_name_diff_content)} names")
    lines.append(f"  Total size: {sum(fd['size'] for fd in file_data):,} bytes")

    # Category breakdown
    lines.append(f"\n  By category:")
    for cat, count in cats.most_common():
        total_size = sum(fd["size"] for fd in file_data if fd["category"] == cat)
        lines.append(f"    {cat:<15} {count:>3} files, {total_size:>6,} bytes")

    # Project breakdown
    lines.append(f"\n  By project:")
    for proj, count in projects.most_common():
        total_size = sum(fd["size"] for fd in file_data if fd["project"] == proj)
        lines.append(f"    {proj:<35} {count:>3} files, {total_size:>6,} bytes")

    # MEMORY.md index files
    indexes = [fd for fd in file_data if fd["category"] == "index"]
    if indexes:
        lines.append(f"\n  MEMORY.md index files ({len(indexes)}):")
        for fd in indexes:
            lines.append(f"    [{fd['project'][:30]}] {fd['header'][:50]}")

    # True duplicates
    if duplicates:
        lines.append(f"\n  True duplicates (identical content):")
        for h, group in duplicates.items():
            lines.append(f"    '{group[0]['name']}' — {len(group)} copies across:")
            for fd in group:
                lines.append(f"      • {fd['project']}")

    # Same name, different content
    if same_name_diff_content:
        lines.append(f"\n  Same filename, different content:")
        for name, group in sorted(same_name_diff_content.items()):
            lines.append(f"    '{name}' ({len(group)} variants):")
            for fd in group:
                lines.append(f"      • [{fd['project'][:30]}] {fd['size']}B — {fd['header'][:60]}")

    # Recommendations
    lines.append(f"\n  ── Recommendations ──")
    if duplicates:
        lines.append(f"  • Remove {sum(len(g) - 1 for g in duplicates.values())} byte-identical duplicate files")
    if len(indexes) > 1:
        lines.append(f"  • Consider consolidating {len(indexes)} MEMORY.md indexes into one per project")
    feedback_count = cats.get("feedback", 0)
    if feedback_count > 3:
        lines.append(f"  • {feedback_count} feedback files — consider merging into a single feedback log per project")
    if not duplicates and len(indexes) <= 1:
        lines.append("  • Memory files are well-organized, no obvious issues")

    return "\n".join(lines)


def memory_inventory() -> str:
    """Print a full inventory of all memory files."""
    files = _find_memory_files()

    lines = []
    lines.append(f"\n┌─ MEMORY FILE INVENTORY ({len(files)} files) {'─' * 30}┐")
    lines.append(f"  {'File':<35} {'Project':<30} {'Size':>8} {'Category'}")
    lines.append("  " + "─" * 90)

    for fp in sorted(files):
        fname = os.path.basename(fp)
        proj = _extract_project(fp)
        cat = _categorize(fname)
        size = os.path.getsize(fp)
        lines.append(f"  {fname:<35} {proj:<30} {size:>8} {cat}")

    return "\n".join(lines)
