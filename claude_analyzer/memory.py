"""Memory file analyzer for Claude session data."""

import os
import glob
import hashlib
from collections import defaultdict, Counter
from typing import Optional

from .parser import project_name_from_path


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


def _extract_project(filepath: str) -> str:
    """Extract project name from a memory file path."""
    return project_name_from_path(filepath, "projects")


def _categorize(filename: str) -> str:
    """Categorize a memory file by naming convention."""
    name = filename.lower().replace(".md", "")
    if name.startswith("feedback_"): return "feedback"
    if name.startswith("project_"): return "project"
    if name.startswith("reference_"): return "reference"
    if name == "memory": return "index"
    if name in ("stakeholders", "user_identity", "dev_environment"): return "meta"
    return "other"


def _read_headers(filepath: str) -> str:
    """Read first line of a memory file."""
    try:
        with open(filepath) as f:
            return f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return "(unreadable)"


def _collect_file_data() -> list:
    """Scan memory files and return structured data."""
    data = []
    for fp in _find_memory_files():
        data.append({
            "path": fp, "name": os.path.basename(fp),
            "project": _extract_project(fp), "category": _categorize(os.path.basename(fp)),
            "size": os.path.getsize(fp), "hash": _hash_file(fp),
            "header": _read_headers(fp),
        })
    return data


def _build_summary(file_data: list, hash_groups: dict, name_groups: dict) -> list:
    """Build summary header lines."""
    unique = len(hash_groups) - sum(1 for g in hash_groups.values() if len(g) > 1)
    dup_redundant = sum(len(g) - 1 for g in hash_groups.values() if len(g) > 1)
    same_name = {n: g for n, g in name_groups.items() if len(g) > 1 and len(set(fd["hash"] for fd in g)) > 1}

    return [
        "\n┌─ MEMORY FILE ANALYSIS ───────────────────────────┐",
        f"  Total files: {len(file_data)}",
        f"  Unique (by content): {unique}",
        f"  True duplicates: {dup_redundant} redundant files",
        f"  Same name, different content: {len(same_name)} names",
        f"  Total size: {sum(fd['size'] for fd in file_data):,} bytes",
    ]


def _build_category_report(file_data: list) -> list:
    """Build category breakdown section."""
    cats = Counter(fd["category"] for fd in file_data)
    lines = ["\n  By category:"]
    for cat, count in cats.most_common():
        total_size = sum(fd["size"] for fd in file_data if fd["category"] == cat)
        lines.append(f"    {cat:<15} {count:>3} files, {total_size:>6,} bytes")
    return lines


def _build_project_report(file_data: list) -> list:
    """Build project breakdown section."""
    projects = Counter(fd["project"] for fd in file_data)
    lines = ["\n  By project:"]
    for proj, count in projects.most_common():
        total_size = sum(fd["size"] for fd in file_data if fd["project"] == proj)
        lines.append(f"    {proj:<35} {count:>3} files, {total_size:>6,} bytes")
    return lines


def _build_indexes_report(file_data: list) -> list:
    """Build MEMORY.md index files section."""
    indexes = [fd for fd in file_data if fd["category"] == "index"]
    if not indexes:
        return []
    lines = [f"\n  MEMORY.md index files ({len(indexes)}):"]
    for fd in indexes:
        lines.append(f"    [{fd['project'][:30]}] {fd['header'][:50]}")
    return lines


def _build_duplicates_report(hash_groups: dict) -> list:
    """Build duplicate file sections."""
    lines = []
    true_dups = {h: g for h, g in hash_groups.items() if len(g) > 1}
    if true_dups:
        lines.append("\n  True duplicates (identical content):")
        for h, group in true_dups.items():
            lines.append(f"    '{group[0]['name']}' — {len(group)} copies across:")
            for fd in group:
                lines.append(f"      • {fd['project']}")
    return lines


def _build_name_conflicts_report(name_groups: dict) -> list:
    """Build same-name-different-content section."""
    conflicts = {n: g for n, g in name_groups.items()
                 if len(g) > 1 and len(set(fd["hash"] for fd in g)) > 1}
    if not conflicts:
        return []
    lines = ["\n  Same filename, different content:"]
    for name, group in sorted(conflicts.items()):
        lines.append(f"    '{name}' ({len(group)} variants):")
        for fd in group:
            lines.append(f"      • [{fd['project'][:30]}] {fd['size']}B — {fd['header'][:60]}")
    return lines


def _build_recommendations(file_data: list, hash_groups: dict) -> list:
    """Build recommendations section."""
    cats = Counter(fd["category"] for fd in file_data)
    dup_count = sum(len(g) - 1 for g in hash_groups.values() if len(g) > 1)
    indexes = [fd for fd in file_data if fd["category"] == "index"]
    lines = ["\n  ── Recommendations ──"]

    if dup_count:
        lines.append(f"  • Remove {dup_count} byte-identical duplicate files")
    if len(indexes) > 1:
        lines.append(f"  • Consider consolidating {len(indexes)} MEMORY.md indexes into one per project")
    if cats.get("feedback", 0) > 3:
        lines.append(f"  • {cats['feedback']} feedback files — consider merging into a single feedback log per project")
    if not dup_count and len(indexes) <= 1:
        lines.append("  • Memory files are well-organized, no obvious issues")
    return lines


def analyze_memory() -> str:
    """Full analysis of all memory files."""
    file_data = _collect_file_data()
    if not file_data:
        return "\n  No memory files found."

    hash_groups = defaultdict(list)
    name_groups = defaultdict(list)
    for fd in file_data:
        hash_groups[fd["hash"]].append(fd)
        name_groups[fd["name"]].append(fd)

    sections = []
    sections.extend(_build_summary(file_data, hash_groups, name_groups))
    sections.extend(_build_category_report(file_data))
    sections.extend(_build_project_report(file_data))
    sections.extend(_build_indexes_report(file_data))
    sections.extend(_build_duplicates_report(hash_groups))
    sections.extend(_build_name_conflicts_report(name_groups))
    sections.extend(_build_recommendations(file_data, hash_groups))

    return "\n".join(sections)


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
