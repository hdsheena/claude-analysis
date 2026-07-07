"""Page: Projects - Per-project breakdown and analysis."""

import streamlit as st

st.set_page_config(
    page_title="Projects - Claude Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.express as px

from shared import load_sessions, get_stats, apply_all_filters, render_sidebar
from claude_analyzer.stats import format_number, format_tokens, format_bytes


st.title("📁 Project Breakdown")

# ── Sidebar & filters ────────────────────────────────────────────────────────

source, project_filter, time_range = render_sidebar()

# ── Load data ────────────────────────────────────────────────────────────────

sessions = load_sessions(source=source)
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No sessions match the filter.")
    st.stop()

stats = get_stats(sessions)

st.caption(
    f"Source: **{source.upper()}** · "
    f"{format_number(stats.total_sessions)} sessions across "
    f"{len(stats.projects)} projects"
)

# ── Project metrics (cached) ─────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner="Building project metrics...")
def _build_project_df(_sessions, _projects_most_common, _project_tokens, _project_size):
    """Build enriched project dataframe."""
    projects = _projects_most_common

    # Build session lookup
    project_sessions_map = {}
    for s in _sessions:
        project_sessions_map.setdefault(s.project, []).append(s)

    rows = []
    for p, c in projects:
        proj_sessions = project_sessions_map.get(p, [])
        avg_msgs = (
            sum(len(s.messages) for s in proj_sessions) // max(len(proj_sessions), 1)
        )
        inp_tok = sum(s.total_input_tokens for s in proj_sessions)
        out_tok = sum(s.total_output_tokens for s in proj_sessions)

        model_counts = {}
        for s in proj_sessions:
            for msg in s.messages:
                if msg.model:
                    model_counts[msg.model] = model_counts.get(msg.model, 0) + 1
        top_model = (
            max(model_counts.items(), key=lambda x: x[1])[0].replace("claude-", "")
            if model_counts
            else ""
        )

        rows.append({
            "Project": p,
            "Sessions": c,
            "Tokens": _project_tokens.get(p, 0),
            "Input Tokens": inp_tok,
            "Output Tokens": out_tok,
            "Disk Size (bytes)": _project_size.get(p, 0),
            "Top Model": top_model,
            "Avg Msgs/Session": avg_msgs,
        })

    return pd.DataFrame(rows)


df_projects = _build_project_df(
    sessions,
    stats.projects.most_common(50),
    stats.project_tokens,
    stats.project_size,
)

# ── Top projects bar chart ──────────────────────────────────────────────────

st.subheader("📊 Top Projects by Sessions")

col1, col2 = st.columns(2)

with col1:
    top_n = min(20, len(df_projects))
    fig = px.bar(
        df_projects.head(top_n),
        x="Sessions",
        y="Project",
        orientation="h",
        color="Tokens",
        color_continuous_scale="blues",
        hover_data={
            "Tokens": True,
            "Top Model": True,
            "Avg Msgs/Session": True,
        },
    )
    fig.update_layout(
        height=500,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    df_by_size = df_projects.sort_values("Disk Size (bytes)", ascending=False).head(top_n)
    fig = px.bar(
        df_by_size,
        x="Disk Size (bytes)",
        y="Project",
        orientation="h",
        color="Disk Size (bytes)",
        color_continuous_scale="greens",
    )
    fig.update_layout(
        height=500,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
    )
    fig.update_xaxes(title="Disk Size")
    st.plotly_chart(fig, use_container_width=True)

# ── Scatter: Sessions vs Tokens ──────────────────────────────────────────────

st.subheader("📈 Sessions vs Tokens (bubble chart)")

fig = px.scatter(
    df_projects.head(30),
    x="Sessions",
    y="Tokens",
    size="Disk Size (bytes)",
    color="Avg Msgs/Session",
    hover_name="Project",
    hover_data={
        "Top Model": True,
        "Disk Size (bytes)": False,
    },
    size_max=40,
    color_continuous_scale="viridis",
)
fig.update_layout(
    height=450,
    margin=dict(l=0, r=0, t=0, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig, use_container_width=True)

# ── Detailed table ───────────────────────────────────────────────────────────

st.divider()
st.subheader("📋 Project Details")

display_df = df_projects.copy()
display_df["Disk Size"] = display_df["Disk Size (bytes)"].apply(format_bytes)
display_df["Tokens (fmt)"] = display_df["Tokens"].apply(format_tokens)
display_df["Sessions (fmt)"] = display_df["Sessions"].apply(format_number)

st.dataframe(
    display_df[
        [
            "Project",
            "Sessions (fmt)",
            "Tokens (fmt)",
            "Disk Size",
            "Top Model",
            "Avg Msgs/Session",
        ]
    ].rename(
        columns={
            "Sessions (fmt)": "Sessions",
            "Tokens (fmt)": "Tokens",
        }
    ),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Project": st.column_config.TextColumn("Project", width="medium"),
        "Sessions": st.column_config.TextColumn("Sessions"),
        "Tokens": st.column_config.TextColumn("Tokens"),
        "Disk Size": st.column_config.TextColumn("Disk Size"),
        "Top Model": st.column_config.TextColumn("Top Model"),
        "Avg Msgs/Session": st.column_config.NumberColumn("Avg Msgs/Session", format="d"),
    },
)
