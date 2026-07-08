"""Page: Compare - Side-by-side session and project comparison."""

import streamlit as st

st.set_page_config(
    page_title="Compare - Claude Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.express as px

from shared import load_sessions, apply_all_filters, render_sidebar
from claude_analyzer.stats import format_tokens, format_number
from claude_analyzer.diff import _session_stats, _aggregate_stats


def _render_model_chart(models: dict, title: str, color: str):
    """Render a horizontal bar chart of model usage."""
    st.subheader(f"🤖 {title}")
    if models:
        df = pd.DataFrame(
            [{"Model": m.replace("claude-", ""), "Calls": c}
             for m, c in models.items()]
        )
        fig = px.bar(df, x="Calls", y="Model", orientation="h",
                     color_discrete_sequence=[color])
        fig.update_layout(
            height=300, margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)


st.title("⚖️ Compare Sessions or Projects")

# ── Sidebar & filters ────────────────────────────────────────────────────────

source, project_filter, time_range = render_sidebar()

st.caption(f"Source: **{source.upper()}**")

# ── Load data ────────────────────────────────────────────────────────────────

sessions = load_sessions(source=source)
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No sessions found.")
    st.stop()

# ── Comparison mode ──────────────────────────────────────────────────────────

mode = st.radio(
    "Compare",
    options=["Sessions", "Projects"],
    horizontal=True,
)

if mode == "Sessions":
    # Build lookup
    session_options = sorted(
        sessions,
        key=lambda s: len(s.messages),
        reverse=True,
    )

    session_labels = [
        f"[{s.source}] {s.project[:20]} — {s.session_id[:12]}... ({len(s.messages)} msgs)"
        for s in session_options
    ]

    col_a, col_b = st.columns(2)

    with col_a:
        idx_a = st.selectbox(
            "Session A",
            options=range(len(session_options)),
            format_func=lambda i: session_labels[i],
            key="session_a",
        )

    with col_b:
        idx_b = st.selectbox(
            "Session B",
            options=range(len(session_options)),
            format_func=lambda i: session_labels[i],
            index=min(1, len(session_options) - 1),
            key="session_b",
        )

    if idx_a == idx_b:
        st.warning("Select two different sessions to compare.")
        st.stop()

    sess_a = session_options[idx_a]
    sess_b = session_options[idx_b]

    a = _session_stats(sess_a)
    b = _session_stats(sess_b)

    # ── Header ─────────────────────────────────────────────────────────

    st.subheader(f"{sess_a.session_id[:12]}...  vs  {sess_b.session_id[:12]}...")

    ca, cb = st.columns(2)
    with ca:
        st.caption(f"**Project:** {sess_a.project}")
        st.caption(f"**Source:** {sess_a.source}")
        if sess_a.first_user_msg:
            st.caption(f"**First msg:** {sess_a.first_user_msg[:100]}")
    with cb:
        st.caption(f"**Project:** {sess_b.project}")
        st.caption(f"**Source:** {sess_b.source}")
        if sess_b.first_user_msg:
            st.caption(f"**First msg:** {sess_b.first_user_msg[:100]}")

    # ── Metrics comparison ──────────────────────────────────────────────

    metrics = [
        ("Messages", a["messages"], b["messages"]),
        ("Lines", a["lines"], b["lines"]),
        ("Input Tokens", a["input_tokens"], b["input_tokens"]),
        ("Output Tokens", a["output_tokens"], b["output_tokens"]),
        ("Cache Read", a["cache_read"], b["cache_read"]),
    ]

    c1, c2, c3, c4, c5 = st.columns(5)
    cols = [c1, c2, c3, c4, c5]

    for i, (label, v1, v2) in enumerate(metrics):
        with cols[i]:
            delta = v1 - v2
            delta_str = f"{delta:+,}" if delta != 0 else "equal"
            st.metric(
                label,
                f"{v1:,}  vs  {v2:,}",
                delta=delta_str,
            )

    # ── Models comparison ───────────────────────────────────────────────

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        _render_model_chart(a["models"], "Models (A)", "#636efa")

    with col2:
        _render_model_chart(b["models"], "Models (B)", "#00cc96")

else:
    # ── Project comparison mode ──────────────────────────────────────────────

    projects = sorted(set(s.project for s in sessions))

    col_a, col_b = st.columns(2)

    with col_a:
        proj_a = st.selectbox("Project A", options=projects, key="proj_a")
    with col_b:
        default_b = projects[1] if len(projects) > 1 else projects[0]
        proj_b = st.selectbox(
            "Project B",
            options=projects,
            index=projects.index(default_b) if default_b in projects else 0,
            key="proj_b",
        )

    if proj_a == proj_b:
        st.warning("Select two different projects to compare.")
        st.stop()

    group_a = [s for s in sessions if s.project == proj_a]
    group_b = [s for s in sessions if s.project == proj_b]

    a = _aggregate_stats(group_a, proj_a)
    b = _aggregate_stats(group_b, proj_b)

    st.subheader(f"{proj_a}  vs  {proj_b}")

    # ── Metrics ──────────────────────────────────────────────────────────────

    metrics = [
        ("Sessions", a["sessions"], b["sessions"]),
        ("Messages", a["messages"], b["messages"]),
        ("Lines", a["lines"], b["lines"]),
        ("Input Tokens", a["input_tokens"], b["input_tokens"]),
        ("Output Tokens", a["output_tokens"], b["output_tokens"]),
        ("Cache Read", a["cache_read"], b["cache_read"]),
    ]

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    cols = [c1, c2, c3, c4, c5, c6]

    for i, (label, v1, v2) in enumerate(metrics):
        with cols[i]:
            delta = v1 - v2
            delta_str = f"{delta:+,}" if delta != 0 else "equal"
            st.metric(
                label,
                f"{v1:,}  vs  {v2:,}",
                delta=delta_str,
            )

    # Efficiency ratio
    a_eff = a["output_tokens"] / max(a["input_tokens"], 1)
    b_eff = b["output_tokens"] / max(b["input_tokens"], 1)
    st.caption(
        f"**Output/Input ratio:** {proj_a}: {a_eff:.1f}x  |  "
        f"{proj_b}: {b_eff:.1f}x"
    )

    # ── Models stacked ───────────────────────────────────────────────────────

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        _render_model_chart(a["models"], f"Models: {proj_a}", "#636efa")

    with col2:
        _render_model_chart(b["models"], f"Models: {proj_b}", "#00cc96")
