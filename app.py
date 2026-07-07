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


# ═══════════════════════════════════════════════════════════════════════════════
# Chart render helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _render_model_chart(stats, source):
    st.subheader(f"📊 Model Usage ({source.upper()})")
    model_items = stats.model_counts.most_common(15)
    df_models = pd.DataFrame([{
        "Model": m.replace("claude-", ""), "Calls": c,
        "Input": format_tokens(stats.model_input_tokens.get(m, 0)),
        "Output": format_tokens(stats.model_output_tokens.get(m, 0)),
    } for m, c in model_items])
    if not df_models.empty:
        fig = px.bar(df_models, x="Calls", y="Model", orientation="h",
                     color="Calls", color_continuous_scale="blues",
                     hover_data=["Input", "Output"])
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)


def _render_tools_chart(stats, source):
    st.subheader(f"🛠️ Top Tools Used ({source.upper()})")
    tool_items = stats.tool_counts.most_common(20)
    if tool_items:
        df_tools = pd.DataFrame(tool_items, columns=["Tool", "Count"])
        fig = px.bar(df_tools, x="Count", y="Tool", orientation="h",
                     color="Count", color_continuous_scale="teal")
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)


def _render_cost_chart(stats, source):
    st.subheader(f"💰 Estimated Cost by Model ({source.upper()})")
    if not stats.model_costs:
        st.caption("No cost data available.")
        return
    cost_items = sorted(stats.model_costs.items(), key=lambda x: -x[1])[:15]
    df_costs = pd.DataFrame([{"Model": m.replace("claude-", ""), "Cost": c} for m, c in cost_items])
    fig = px.bar(df_costs, x="Cost", y="Model", orientation="h",
                 color="Cost", color_continuous_scale="reds", text_auto=".2f")
    fig.update_traces(texttemplate="$%{x:,.2f}", textposition="outside")
    fig.update_layout(height=400, margin=dict(l=0, r=80, t=0, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis=dict(autorange="reversed"), coloraxis_showscale=False,
                      xaxis_title="Estimated Cost (USD)")
    st.plotly_chart(fig, use_container_width=True)


def _render_project_chart(stats, source):
    st.subheader(f"📁 Projects by Session Count ({source.upper()})")
    proj_items = stats.projects.most_common(15)
    if not proj_items:
        return
    df_projects = pd.DataFrame([{
        "Project": p[:40], "Sessions": c,
        "Tokens": format_tokens(stats.project_tokens.get(p, 0)),
    } for p, c in proj_items])
    fig = px.bar(df_projects, x="Sessions", y="Project", orientation="h",
                 color="Sessions", color_continuous_scale="purples", hover_data=["Tokens"])
    fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)


def _render_length_distribution(stats):
    st.subheader("📏 Session Length Distribution")
    lengths = sorted(stats.session_lengths)
    if not lengths:
        return
    df_lens = pd.DataFrame({"Messages per session": lengths})
    fig = px.histogram(df_lens, x="Messages per session", nbins=30,
                       color_discrete_sequence=["#636efa"], marginal="box")
    fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def _render_stop_reasons(stats):
    st.subheader("🛑 Stop Reasons")
    stop_items = stats.stop_reasons.most_common(10)
    if not stop_items:
        return
    df_stops = pd.DataFrame(stop_items, columns=["Reason", "Count"])
    fig = px.pie(df_stops, names="Reason", values="Count", hole=0.4)
    fig.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0),
                      paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)


def _render_footer():
    st.divider()
    st.caption(f"Last parsed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • "
               "Use the sidebar to navigate between views or refresh data.")


# ═══════════════════════════════════════════════════════════════════════════════
# Page entry point
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Claude Code Analytics", page_icon="🔬",
                   layout="wide", initial_sidebar_state="expanded")

source, project_filter, time_range = render_sidebar()

sessions = load_sessions(source=source)
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No sessions found. Try adjusting your filter or source.")
    st.stop()

stats = get_stats(sessions)

st.title("🔬 Claude Code Session Analytics")
st.caption(f"Source: **{source.upper()}** · "
           f"{format_number(stats.total_sessions)} sessions across "
           f"{len(stats.projects)} projects"
           f"{'' if time_range == 'All time' else f' • {time_range}'}")

# Metrics row
c1, c2, c3, c4, c5 = st.columns(5)
total_tokens = stats.total_input_tokens + stats.total_output_tokens
avg_msgs = stats.total_messages // stats.total_sessions if stats.total_sessions else 0
top_model = stats.model_counts.most_common(1)
top_name = top_model[0][0].replace("claude-", "") if top_model else "N/A"
top_calls = f"{top_model[0][1]} calls" if top_model else ""

with c1: st.metric("Total Sessions", format_number(stats.total_sessions), delta=f"{len(stats.projects)} projects")
with c2: st.metric("Total Tokens", format_tokens(total_tokens), delta=f"{format_tokens(stats.total_output_tokens)} output")
with c3: st.metric("Estimated Cost", f"${stats.estimated_cost:,.2f}", delta=f"{stats.cache_hit_ratio:.1f}% cache hit")
with c4: st.metric("Total Messages", format_number(stats.total_messages), delta=f"~{avg_msgs}/session")
with c5: st.metric("Top Model", top_name[:20], delta=top_calls)

st.divider()

# Charts row
col_l, col_r = st.columns(2)
with col_l: _render_model_chart(stats, source)
with col_r: _render_tools_chart(stats, source)

st.divider()
_render_cost_chart(stats, source)

col_l2, col_r2 = st.columns(2)
with col_l2: _render_project_chart(stats, source)
with col_r2: _render_length_distribution(stats)

# Quick stats
st.divider()
st.subheader("📋 Quick Stats")
ca, cb, cc, cd = st.columns(4)
with ca:
    st.metric("Total Lines", format_number(stats.total_lines))
    st.metric("Disk Size", f"{stats.total_size_mb:.1f} MB")
with cb:
    st.metric("Cache Read", format_tokens(stats.total_cache_read))
    st.metric("Cache Created", format_tokens(stats.total_cache_create))
with cc:
    st.metric("Input Tokens", format_tokens(stats.total_input_tokens))
    st.metric("Output Tokens", format_tokens(stats.total_output_tokens))
with cd:
    st.metric("Projects Source", stats.projects_source_count)
    st.metric("Local Agent", stats.local_agent_count)

st.divider()
_render_stop_reasons(stats)
_render_footer()
