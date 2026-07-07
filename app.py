#!/usr/bin/env python3
"""Streamlit app for Claude Code session analysis.

Usage:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

from shared import load_sessions, get_stats, apply_all_filters, render_sidebar
from claude_analyzer.stats import format_number, format_tokens

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Claude Code Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────

source, project_filter, time_range = render_sidebar()

# ── Load data ────────────────────────────────────────────────────────────────

sessions = load_sessions(source=source)
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No sessions found. Try adjusting your filter or source.")
    st.stop()

stats = get_stats(sessions)

# ── Summary Dashboard ────────────────────────────────────────────────────────

st.title("🔬 Claude Code Session Analytics")
st.caption(f"Source: **{source.upper()}** · "
           f"{format_number(stats.total_sessions)} sessions across "
           f"{len(stats.projects)} projects"
           f"{'' if time_range == 'All time' else f' • {time_range}'}")

# Top-level metrics row
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "Total Sessions",
        format_number(stats.total_sessions),
        delta=f"{len(stats.projects)} projects",
    )

with col2:
    total_tokens = stats.total_input_tokens + stats.total_output_tokens
    st.metric(
        "Total Tokens",
        format_tokens(total_tokens),
        delta=f"{format_tokens(stats.total_output_tokens)} output",
    )

with col3:
    st.metric(
        "Estimated Cost",
        f"${stats.estimated_cost:,.2f}",
        delta=f"{stats.cache_hit_ratio:.1f}% cache hit",
    )

with col4:
    avg_msgs = (stats.total_messages // stats.total_sessions
                if stats.total_sessions else 0)
    st.metric(
        "Total Messages",
        format_number(stats.total_messages),
        delta=f"~{avg_msgs}/session",
    )

with col5:
    top_model = stats.model_counts.most_common(1)
    top_model_name = top_model[0][0].replace("claude-", "") if top_model else "N/A"
    st.metric(
        "Top Model",
        top_model_name[:20],
        delta=f"{top_model[0][1]} calls" if top_model else "",
    )

st.divider()

# ── Charts row ───────────────────────────────────────────────────────────────

col_left, col_right = st.columns(2)

with col_left:
    st.subheader(f"📊 Model Usage ({source.upper()})")

    model_items = stats.model_counts.most_common(15)
    df_models = pd.DataFrame(
        [
            {
                "Model": m.replace("claude-", ""),
                "Calls": c,
                "Input": format_tokens(stats.model_input_tokens.get(m, 0)),
                "Output": format_tokens(stats.model_output_tokens.get(m, 0)),
            }
            for m, c in model_items
        ]
    )
    if not df_models.empty:
        fig = px.bar(
            df_models,
            x="Calls",
            y="Model",
            orientation="h",
            color="Calls",
            color_continuous_scale="blues",
            hover_data=["Input", "Output"],
        )
        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader(f"🛠️ Top Tools Used ({source.upper()})")

    tool_items = stats.tool_counts.most_common(20)
    if tool_items:
        df_tools = pd.DataFrame(tool_items, columns=["Tool", "Count"])
        fig = px.bar(
            df_tools,
            x="Count",
            y="Tool",
            orientation="h",
            color="Count",
            color_continuous_scale="teal",
        )
        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

# ── Cost by model ────────────────────────────────────────────────────────────

st.divider()
st.subheader(f"💰 Estimated Cost by Model ({source.upper()})")

if stats.model_costs:
    cost_items = sorted(stats.model_costs.items(), key=lambda x: -x[1])[:15]
    df_costs = pd.DataFrame(
        [
            {
                "Model": m.replace("claude-", ""),
                "Cost": c,
            }
            for m, c in cost_items
        ]
    )
    fig_cost = px.bar(
        df_costs,
        x="Cost",
        y="Model",
        orientation="h",
        color="Cost",
        color_continuous_scale="reds",
        text_auto=".2f",
    )
    fig_cost.update_traces(
        texttemplate="$%{x:,.2f}",
        textposition="outside",
    )
    fig_cost.update_layout(
        height=400,
        margin=dict(l=0, r=80, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(autorange="reversed"),
        coloraxis_showscale=False,
        xaxis_title="Estimated Cost (USD)",
    )
    st.plotly_chart(fig_cost, use_container_width=True)
else:
    st.caption("No cost data available.")

# ── Projects & Session Distribution ──────────────────────────────────────────

col_left2, col_right2 = st.columns(2)

with col_left2:
    st.subheader(f"📁 Projects by Session Count ({source.upper()})")

    proj_items = stats.projects.most_common(15)
    if proj_items:
        df_projects = pd.DataFrame(
            [
                {
                    "Project": p[:40],
                    "Sessions": c,
                    "Tokens": format_tokens(
                        stats.project_tokens.get(p, 0)
                    ),
                }
                for p, c in proj_items
            ]
        )
        fig = px.bar(
            df_projects,
            x="Sessions",
            y="Project",
            orientation="h",
            color="Sessions",
            color_continuous_scale="purples",
            hover_data=["Tokens"],
        )
        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

with col_right2:
    st.subheader("📏 Session Length Distribution")

    lengths = sorted(stats.session_lengths)
    if lengths:
        df_lens = pd.DataFrame({"Messages per session": lengths})
        fig = px.histogram(
            df_lens,
            x="Messages per session",
            nbins=30,
            color_discrete_sequence=["#636efa"],
            marginal="box",
        )
        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

# ── Additional stats ─────────────────────────────────────────────────────────

st.divider()
st.subheader("📋 Quick Stats")

col_a, col_b, col_c, col_d = st.columns(4)

with col_a:
    st.metric("Total Lines", format_number(stats.total_lines))
    st.metric(
        "Disk Size",
        f"{stats.total_size_mb:.1f} MB",
    )

with col_b:
    st.metric(
        "Cache Read",
        format_tokens(stats.total_cache_read),
    )
    st.metric(
        "Cache Created",
        format_tokens(stats.total_cache_create),
    )

with col_c:
    st.metric(
        "Input Tokens",
        format_tokens(stats.total_input_tokens),
    )
    st.metric(
        "Output Tokens",
        format_tokens(stats.total_output_tokens),
    )

with col_d:
    st.metric(
        "Projects Source",
        stats.projects_source_count,
    )
    st.metric(
        "Local Agent",
        stats.local_agent_count,
    )

# ── Stop reasons ─────────────────────────────────────────────────────────────

st.divider()
st.subheader("🛑 Stop Reasons")

stop_items = stats.stop_reasons.most_common(10)
if stop_items:
    df_stops = pd.DataFrame(stop_items, columns=["Reason", "Count"])
    fig = px.pie(
        df_stops,
        names="Reason",
        values="Count",
        hole=0.4,
    )
    fig.update_layout(
        height=350,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Footer ───────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    f"Last parsed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • "
    f"Use the sidebar to navigate between views or refresh data."
)
