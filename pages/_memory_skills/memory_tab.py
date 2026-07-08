"""Memory tab — scan and display memory files across projects."""

import streamlit as st
import pandas as pd
import plotly.express as px
from collections import defaultdict

from claude_analyzer.memory import collect_memory_file_data


def render() -> None:
    """Scan and display memory files across projects."""
    st.subheader("📝 Memory File Analysis")

    file_data = collect_memory_file_data()

    if not file_data:
        st.info("No memory files found.")
        return

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
