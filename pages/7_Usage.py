"""Page: Usage & Pace - burn rate, month-end projection, and optional caps."""

import streamlit as st

st.set_page_config(
    page_title="Usage & Pace - Claude Analytics", page_icon="⚡",
    layout="wide", initial_sidebar_state="expanded",
)

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go

from shared import load_sessions, apply_all_filters, render_sidebar
from claude_analyzer.usage import (
    METRIC_REQUESTS, METRIC_TOKENS, DEFAULT_CAPS_PATH,
    compute_source_burns, load_caps, project_caps, save_caps,
)


SOURCE_COLORS = {
    "claude": "#636efa", "mimo": "#00cc96", "opencode": "#ab63fa",
    "freebuff": "#ffa15a", "antigravity": "#19d3f3",
    "copilot": "#22e584", "codex": "#4ec9b0",
}


def _fmt(v, metric: str) -> str:
    if metric == METRIC_TOKENS:
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"{v / 1_000:.0f}K"
        return str(int(v))
    return f"{int(v):,}"


def _pace_label(b) -> str:
    p = b["pace_change_pct"]
    return "—" if p is None else f"{p:+.0f}%"


def _render_kpis(burns) -> None:
    for src, b in sorted(burns.items()):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"{src} · MTD", _fmt(b["mtd"], b["metric"]))
        c2.metric("Proj. month-end", _fmt(b["proj_month_end"], b["metric"]),
                  _pace_label(b))
        c3.metric("Avg/day (30d)", _fmt(b["avg30"], b["metric"]))
        c4.metric("Last month", _fmt(b["last_month"], b["metric"]))


def _render_daily_charts(burns) -> None:
    today = date.today()
    start = today - timedelta(days=59)
    days = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(60)]

    token_rows = {s: b for s, b in burns.items() if b["metric"] == METRIC_TOKENS}
    req_rows = {s: b for s, b in burns.items() if b["metric"] == METRIC_REQUESTS}

    df = pd.DataFrame({"Date": pd.to_datetime(days)})
    for src, b in token_rows.items():
        df[src] = [b["days"].get(d, 0) for d in days]

    cols = st.columns(2)
    with cols[0]:
        st.subheader("📊 Daily Tokens (60d)")
        if token_rows:
            fig = go.Figure()
            for src in sorted(token_rows):
                fig.add_trace(go.Scatter(
                    x=df["Date"], y=df[src], mode="lines", name=src.capitalize(),
                    stackgroup="one", line=dict(width=0.5, color=SOURCE_COLORS.get(src)),
                    hovertemplate="%{x|%b %d}<br>%{y:,.0f}<extra></extra>",
                ))
            fig.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0),
                              paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                              legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No token data for this source.")
    with cols[1]:
        st.subheader("🔢 Daily AI Calls (60d)")
        if req_rows:
            fig = go.Figure()
            for src in sorted(req_rows):
                fig.add_trace(go.Bar(
                    x=df["Date"], y=[req_rows[src]["days"].get(d, 0) for d in days],
                    name=src.capitalize(), marker_color=SOURCE_COLORS.get(src, "#888"),
                    hovertemplate="%{x|%b %d}<br>%{y}<extra></extra>",
                ))
            fig.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0),
                              paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                              barmode="stack",
                              legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No request-count sources in this filter.")


def _render_hourly_heatmap(burns) -> None:
    token_rows = [b for b in burns.values() if b["metric"] == METRIC_TOKENS]
    if not token_rows:
        return
    st.subheader("🕐 Hourly Burn (last 30d, % of that source's busiest hour)")
    labels, z = [], []
    for b in sorted(token_rows, key=lambda x: -max(x["hourly"].values(), default=0)):
        raw = [b["hourly"].get(h, 0) for h in range(24)]
        mx = max(raw) or 1
        labels.append(b["source"])
        z.append([v / mx * 100 for v in raw])
    fig = go.Figure(data=go.Heatmap(
        z=z, y=labels, x=[f"{h:02d}" for h in range(24)],
        colorscale="Viridis", zmin=0, zmax=100,
        hovertemplate="%{y} · %{x}:00 — %{z:.0f}%<extra></extra>",
    ))
    fig.update_layout(height=180 + 34 * len(labels), margin=dict(l=0, r=0, t=0, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)


def _render_caps(burns) -> None:
    st.divider()
    st.subheader("⚙️ Quota Caps → 'days left'")
    st.caption(
        f"Caps live in `{DEFAULT_CAPS_PATH}`. Set a cap (0 = disabled) for any "
        "source whose limit you know; 'days left' = remaining ÷ recent 30-day "
        "average daily burn. For a **month** cap you may set a **reset day** "
        "(1-31) to track a billing-cycle window instead of the calendar month — "
        "GitHub Copilot and OpenAI Codex allowances reset on the subscription "
        "anniversary, not the 1st. Server-side limits we can't read locally "
        "(e.g. Claude's 5x) are pace-only until you add a cap.")

    caps = load_caps()
    with st.form("caps_form"):
        updated = dict(caps)
        for src, b in sorted(burns.items()):
            cur = caps.get(src, {})
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            c1.markdown(f"**{src}** — {b['metric']}")
            cap_val = c2.number_input(
                f"{src} cap", value=float(cur.get("cap", 0) or 0),
                min_value=0.0, step=1000.0, key=f"cap_{src}", format="%.0f",
                label_visibility="collapsed",
                help=f"Quota cap for {src} ({b['metric']} per period). 0 = disabled.")
            period = c3.selectbox(
                f"{src} period", ["month", "week"],
                index=0 if cur.get("period", "month") == "month" else 1,
                key=f"per_{src}", label_visibility="collapsed")
            rd_val = int(c4.number_input(
                f"{src} reset day", value=int(cur.get("reset_day", 1) or 1),
                min_value=1, max_value=31, step=1, key=f"rd_{src}",
                label_visibility="collapsed",
                help="Billing-cycle reset day (month caps only). Ignored for week."))
            if cap_val > 0:
                cfg = {"metric": b["metric"], "cap": int(cap_val),
                       "period": period}
                if period == "month":
                    cfg["reset_day"] = rd_val
                updated[src] = cfg
            else:
                updated.pop(src, None)
        if st.form_submit_button("💾 Save caps"):
            path = save_caps(updated)
            caps = updated
            st.success(f"Saved to {path}")

    proj = project_caps(burns, caps)
    if proj:
        st.subheader("📉 Projected usage vs caps")
        df = pd.DataFrame(proj).sort_values("pct_used", ascending=False)
        has_cycle = any(p.get("reset_day") for p in proj)
        col_cfg = {
            "source": st.column_config.TextColumn("Source"),
            "metric": st.column_config.TextColumn("Metric"),
            "period": st.column_config.TextColumn("Period"),
            "used": st.column_config.NumberColumn("Used"),
            "cap": st.column_config.NumberColumn("Cap"),
            "pct_used": st.column_config.NumberColumn("% Used", format="%.1f%%"),
            "remaining": st.column_config.NumberColumn("Remaining"),
            "projected": st.column_config.NumberColumn("Proj. period-end"),
            "days_left": st.column_config.NumberColumn("Days left",
                                                       format="%.1f"),
            "projected_over_cap": st.column_config.CheckboxColumn("Over cap?"),
            "est_exhaust_date": st.column_config.TextColumn("Est. exhaust"),
        }
        if has_cycle:
            col_cfg.update({
                "reset_day": st.column_config.NumberColumn("Reset day"),
                "cycle_start": st.column_config.TextColumn("Cycle start"),
                "cycle_end": st.column_config.TextColumn("Cycle end"),
            })
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config=col_cfg)
    else:
        st.caption("No caps set — enter caps above to see 'days left' estimates.")


st.title("⚡ Usage & Pace")
st.caption("Burn rate, projected month-end, and estimated time remaining — "
           "extrapolated from local session history, not a quota API.")

source, project_filter, time_range = render_sidebar()

sessions = load_sessions(source=source)
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No sessions match the filter.")
    st.stop()


@st.cache_data(ttl=3600, show_spinner="Computing burn rates...")
def _compute_burns(_sessions):
    return compute_source_burns(_sessions)


burns = _compute_burns(sessions)

if not burns:
    st.warning("No timestamped sessions with usage data found.")
    st.stop()

st.caption(f"Source: **{source.upper()}** · {len(sessions)} sessions · "
           f"metric per source: tokens (in+out+cache) or AI-call count")

_render_kpis(burns)
_render_daily_charts(burns)
_render_hourly_heatmap(burns)
_render_caps(burns)
