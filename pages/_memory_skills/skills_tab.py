"""Skills tab — display installed skills from ~/.claude/skills."""

import os
import pandas as pd
import streamlit as st


def render() -> None:
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
            except (OSError, UnicodeDecodeError):
                entry["Preview"] = "(unreadable)"
        if is_symlink:
            try:
                entry["Target"] = os.readlink(full)[:80]
            except (OSError, AttributeError):
                entry["Target"] = "?"

        skill_data.append(entry)

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
