"""Page: Timeline - Interactive time-series charts for Claude usage."""

import streamlit as st

st.set_page_config(
    page_title="Timeline - Claude Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from shared import load_sessions, apply_all_filters, render_sidebar
from claude_analyzer.timeline import compute_timeline


st.title("🗓️ Usage Timeline")

# ── Sidebar & filters ────────────────────────────────────────────────────────

source, project_filter, time_range = render_sidebar()

# ── Load data ────────────────────────────────────────────────────────────────

sessions = load_sessions(source=source)
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No sessions match the filter.")
    st.stop()

# ── Bucket selector ──────────────────────────────────────────────────────────

bucket = st.radio(
    "Time bucket",
    options=["daily", "weekly", "monthly"],
    horizontal=True,
    index=1,
)

# ── Compute timeline (cached) ────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner="Computing timeline...")
def _compute_timeline(_sessions, bucket):
    return compute_timeline(_sessions, bucket)

tl = _compute_timeline(sessions, bucket)

if not tl["dates"]:
    st.warning(
        "No dated sessions found. Sessions need registry entries "
        "(~/.claude/sessions/*.json) with timestamps for timeline analysis."
    )
    st.stop()

# Warn if all token values are zero (e.g., Freebuff doesn't record tokens)
if sum(tl["tokens"]) == 0:
    st.info(
        "ℹ️ No token data available for this source or time range. "
        "Token-based charts and cost estimates will be unavailable, "
        "but session counts and date-based data are still shown below."
    )
    zero_tokens = True
else:
    zero_tokens = False

# Build dataframe with optional per-source token columns
if tl.get("tokens_by_source"):
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(tl["dates"]),
            "Tokens": tl["tokens"],
            **{src.capitalize(): vals for src, vals in tl["tokens_by_source"].items()},
            "Sessions": tl["sessions"],
            "Cost ($)": tl["cost"],
        }
    )
    # Reorder: Date, source columns, Tokens, Sessions, Cost
    src_cols = [src.capitalize() for src in tl["tokens_by_source"].keys()]
    col_order = ["Date"] + src_cols + ["Tokens", "Sessions", "Cost ($)"]
    df = df[col_order]
else:
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(tl["dates"]),
            "Tokens": tl["tokens"],
            "Sessions": tl["sessions"],
            "Cost ($)": tl["cost"],
        }
    )

st.caption(
    f"Source: **{source.upper()}** · "
    f"{len(df)} {bucket} periods • "
    f"{tl['dates'][0]} → {tl['dates'][-1]}"
)

# ── Tokens over time ─────────────────────────────────────────────────────────

if not zero_tokens:
    st.subheader("📊 Token Usage Over Time")

    source_colors = {
        "claude": "#636efa",
        "mimo": "#00cc96",
        "opencode": "#ab63fa",
        "freebuff": "#ffa15a",
        "antigravity": "#19d3f3",
    }
    tokens_by_src = tl.get("tokens_by_source", {})

    if tokens_by_src and len(tokens_by_src) > 1:
        # Stacked area by source + total line
        fig_tokens = go.Figure()

        for src_label in sorted(tokens_by_src.keys()):
            color = source_colors.get(src_label, "#888")
            fig_tokens.add_trace(
                go.Scatter(
                    x=df["Date"],
                    y=tokens_by_src[src_label],
                    mode="lines",
                    name=src_label.capitalize(),
                    stackgroup="one",
                    line=dict(width=0.5, color=color),
                    hovertemplate="%{x|%b %d, %Y}<br>" + src_label.capitalize() + ": %{y:,.0f}<extra></extra>",
                )
            )

        # Total line on top
        fig_tokens.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["Tokens"],
                mode="lines+markers",
                name="Total",
                line=dict(color="#ffffff", width=2, dash="dot"),
                marker=dict(size=4),
                hovertemplate="%{x|%b %d, %Y}<br>Total: %{y:,.0f}<extra></extra>",
            )
        )

        fig_tokens.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
    else:
        # Single source — simple line chart
        fig_tokens = go.Figure()
        fig_tokens.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["Tokens"],
                mode="lines+markers",
                name="Total Tokens",
                fill="tozeroy",
                line=dict(color="#636efa", width=2),
                hovertemplate="%{x|%b %d, %Y}<br>Tokens: %{y:,.0f}<extra></extra>",
            )
        )
        fig_tokens.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
        )
    st.plotly_chart(fig_tokens, use_container_width=True)

# ── Sessions + Cost ──────────────────────────────────────────────────────────

if not zero_tokens:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔢 Sessions per Period")

        fig_sessions = px.bar(
            df,
            x="Date",
            y="Sessions",
            color_discrete_sequence=["#00cc96"],
        )
        fig_sessions.update_layout(
            height=350,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_sessions, use_container_width=True)

    with col2:
        st.subheader("💰 Cost Over Time")

        fig_cost = go.Figure()
        fig_cost.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["Cost ($)"],
                mode="lines+markers",
                name="Cost",
                fill="tozeroy",
                line=dict(color="#ab63fa", width=2),
                hovertemplate="%{x|%b %d, %Y}<br>Cost: $%{y:.2f}<extra></extra>",
            )
        )
        fig_cost.update_layout(
            height=350,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_cost, use_container_width=True)
else:
    st.subheader("🔢 Sessions per Period")

    fig_sessions = px.bar(
        df,
        x="Date",
        y="Sessions",
        color_discrete_sequence=["#00cc96"],
    )
    fig_sessions.update_layout(
        height=350,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_sessions, use_container_width=True)

# ── Model trends ─────────────────────────────────────────────────────────────

if not zero_tokens and tl.get("top_models"):
    st.subheader("🤖 Model Usage Trends")

    model_cols = [m.replace("claude-", "") for m in tl["top_models"].keys()]
    if model_cols:
        fig_models = go.Figure()
        colors = ["#636efa", "#00cc96", "#ab63fa", "#ffa15a", "#19d3f3"]

        for i, (model, values) in enumerate(tl["top_models"].items()):
            short = model.replace("claude-", "")
            fig_models.add_trace(
                go.Scatter(
                    x=df["Date"],
                    y=values,
                    mode="lines",
                    name=short,
                    stackgroup="one",
                    line=dict(width=0.5, color=colors[i % len(colors)]),
                    hovertemplate="%{x|%b %d}<br>"
                    + short
                    + ": %{y}<extra></extra>",
                )
            )

        fig_models.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_models, use_container_width=True)

# ── Cache hit rate ──────────────────────────────────────────────────────

if not zero_tokens:
    cache_read = tl.get("cache_read", [])
    cache_write = tl.get("cache_write", [])
    if cache_read or cache_write:
        st.subheader("💾 Cache Hit Rate Over Time")

        df_cache = pd.DataFrame({
            "Date": pd.to_datetime(tl["dates"]),
            "Cache Read": cache_read,
            "Cache Write": cache_write,
        })
        total_cache = [r + w for r, w in zip(cache_read, cache_write)]
        df_cache["Hit Rate (%)"] = [
            (r / t * 100) if t > 0 else 0
            for r, t in zip(cache_read, total_cache)
        ]

        col_c1, col_c2 = st.columns(2)

        with col_c1:
            fig_cache = go.Figure()
            fig_cache.add_trace(go.Scatter(
                x=df_cache["Date"],
                y=df_cache["Cache Read"],
                mode="lines+markers",
                name="Cache Read",
                fill="tozeroy",
                line=dict(color="#00cc96", width=2),
                hovertemplate="%{x|%b %d}<br>Cache Read: %{y:,.0f}<extra></extra>",
            ))
            fig_cache.add_trace(go.Scatter(
                x=df_cache["Date"],
                y=df_cache["Cache Write"],
                mode="lines+markers",
                name="Cache Write",
                fill="tozeroy",
                line=dict(color="#ffa15a", width=2),
                hovertemplate="%{x|%b %d}<br>Cache Write: %{y:,.0f}<extra></extra>",
            ))
            fig_cache.update_layout(
                height=350,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_cache, use_container_width=True)

        with col_c2:
            fig_rate = go.Figure()
            fig_rate.add_trace(go.Scatter(
                x=df_cache["Date"],
                y=df_cache["Hit Rate (%)"],
                mode="lines+markers",
                name="Hit Rate %",
                fill="tozeroy",
                line=dict(color="#ab63fa", width=2),
                hovertemplate="%{x|%b %d}<br>Hit Rate: %{y:.1f}%<extra></extra>",
            ))
            fig_rate.add_hline(
                y=90, line_dash="dash", line_color="gray",
                annotation_text="90%", annotation_position="right",
            )
            fig_rate.update_layout(
                height=350,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(range=[0, 105], ticksuffix="%"),
            )
            st.plotly_chart(fig_rate, use_container_width=True)

# ── Raw data table ───────────────────────────────────────────────────────

st.divider()
st.subheader("📋 Raw Timeline Data")

st.dataframe(
    df.sort_values("Date", ascending=False),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
        "Tokens": st.column_config.NumberColumn("Tokens"),
        "Sessions": st.column_config.NumberColumn("Sessions"),
        "Cost ($)": st.column_config.NumberColumn("Cost", format="$%.2f"),
        **{
            src.capitalize(): st.column_config.NumberColumn(src.capitalize())
            for src in (tl.get("tokens_by_source") or {}).keys()
        },
    },
)

# ── Model breakdown table ───────────────────────────────────────────────

if tl.get("top_models"):
    st.subheader("🧪 Model Breakdown")

    mdf = pd.DataFrame({"Date": pd.to_datetime(tl["dates"])})
    for model, values in tl["top_models"].items():
        short = model.replace("claude-", "")
        mdf[short] = values

    st.dataframe(
        mdf.sort_values("Date", ascending=False),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            **{
                col: st.column_config.NumberColumn(col)
                for col in mdf.columns if col != "Date"
            },
        },
    )
