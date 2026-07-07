"""Page: Antigravity Sessions — view conversations with thinking/reasoning."""

import streamlit as st

st.set_page_config(
    page_title="Antigravity Sessions - Claude Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
from datetime import datetime

from shared import load_sessions, apply_all_filters, render_sidebar


st.title("🧠 Antigravity Sessions")

source, project_filter, time_range = render_sidebar()
if source not in ("antigravity", "all"):
    st.info("👈 Select **antigravity** from the sidebar to view Antigravity sessions.")
    st.stop()

sessions = load_sessions(source="antigravity")
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No Antigravity sessions found.")
    st.stop()

# ── Search / filter ──────────────────────────────────────────────────────

search_text = st.text_input(
    "🔍 Search sessions by prompt or project",
    placeholder="e.g. 'evc' or 'deploy script'",
    key="ag_search",
)

filtered = sessions
if search_text.strip():
    q = search_text.strip().lower()
    filtered = [
        s for s in sessions
        if q in (s.first_user_msg or "").lower()
        or q in s.project.lower()
    ]

if not filtered:
    st.info(f"No sessions matching '{search_text}'. Try a different query.")
    st.stop()

# ── Session selector ─────────────────────────────────────────────────────

session_options = {}
for s in filtered:
    ts = s.started_at
    date_str = datetime.fromtimestamp(ts if ts < 1e12 else ts / 1000).strftime("%Y-%m-%d") if ts else "?"
    label = f"[{date_str}] {s.project} — {(s.first_user_msg or s.session_id)[:80]}"
    session_options[label] = s.session_id

selected_label = st.selectbox(
    f"{len(session_options)} sessions" + (f" matching '{search_text}'" if search_text.strip() else ""),
    options=list(session_options.keys()),
    index=0,
)

selected_id = session_options[selected_label]
sess = next(s for s in filtered if s.session_id == selected_id)

# ── Session header ───────────────────────────────────────────────────────

ts = sess.started_at
date_str = datetime.fromtimestamp(ts if ts < 1e12 else ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "unknown"

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Project", sess.project)
with c2:
    st.metric("Date", date_str)
with c3:
    st.metric("Messages", len(sess.messages))

if sess.first_user_msg:
    st.caption(f"**First prompt:** {sess.first_user_msg[:300]}")

st.divider()

# ── Conversation view ────────────────────────────────────────────────────

user_msgs = [m for m in sess.messages if m.msg_type == "user"]
assistant_msgs = [m for m in sess.messages if m.msg_type == "assistant"]

st.caption(f"💬 {len(user_msgs)} user · 🤖 {len(assistant_msgs)} assistant · "
           f"📄 {len(sess.messages)} total entries")

view_mode = st.radio("View", ["Conversation", "Raw JSON"], horizontal=True, index=0)

with st.container(height=600, border=True):
    if view_mode == "Conversation":
        for i, msg in enumerate(sess.messages):
            raw = msg._raw
            created = raw.get("created_at", "")[:19].replace("T", " ")

            if msg.msg_type == "user":
                content = raw.get("content", "")
                with st.chat_message("user"):
                    if created:
                        st.caption(f"_{created}_")
                    if isinstance(content, str):
                        st.markdown(content[:2000])
                    else:
                        st.text(str(content)[:2000])

            elif msg.msg_type == "assistant":
                with st.chat_message("assistant"):
                    if created:
                        st.caption(f"_{created}_")

                    thinking = raw.get("thinking", "")
                    tool_calls = raw.get("tool_calls", [])

                    if thinking:
                        with st.expander("🧠 Thinking", expanded=False):
                            st.markdown(thinking[:5000])

                    if isinstance(tool_calls, list) and tool_calls:
                        st.caption("🛠️ **Tool calls:**")
                        for tc in tool_calls:
                            if isinstance(tc, dict):
                                tc_name = tc.get("name", "?")
                                with st.expander(f"  • {tc_name}", expanded=False):
                                    st.caption("**Arguments:**")
                                    st.json(tc.get("args", {}) if isinstance(tc.get("args"), dict) else str(tc.get("args", ""))[:2000])

                    content = raw.get("content", "")
                    if content:
                        if isinstance(content, str):
                            st.markdown(content[:3000])
                        else:
                            st.text(str(content)[:3000])
    else:
        # Raw JSON view
        st.json([m._raw for m in sess.messages])

# ── Thinking-only view ──────────────────────────────────────────────────

st.divider()
st.subheader("🧠 All Thinking Blocks")
thinking_msgs = [
    m for m in sess.messages
    if m.msg_type == "assistant" and m._raw.get("thinking")
]
if thinking_msgs:
    for i, m in enumerate(thinking_msgs):
        raw = m._raw
        created = raw.get("created_at", "")[:19].replace("T", " ")
        with st.expander(f"Thinking #{i + 1} — {created}", expanded=i == 0):
            st.markdown(raw["thinking"][:10000])
else:
    st.caption("No thinking blocks in this session.")

# ── Session list ────────────────────────────────────────────────────────

st.divider()
st.subheader("📋 All Antigravity Sessions")

rows = []
for s in filtered:
    ts = s.started_at
    date_str = datetime.fromtimestamp(ts if ts < 1e12 else ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "?"
    assistant_count = sum(1 for m in s.messages if m.msg_type == "assistant")
    thinking_count = sum(1 for m in s.messages if m.msg_type == "assistant" and m._raw.get("thinking"))
    rows.append({
        "Session ID": s.session_id[:12] + "...",
        "Project": s.project,
        "Date": date_str,
        "Messages": len(s.messages),
        "Assistant": assistant_count,
        "Thinking": thinking_count,
        "First prompt": (s.first_user_msg or "")[:100],
    })

df = pd.DataFrame(rows)
st.dataframe(
    df.sort_values("Date", ascending=False),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Session ID": st.column_config.TextColumn("ID"),
        "Project": st.column_config.TextColumn("Project"),
        "Date": st.column_config.TextColumn("Date"),
        "Messages": st.column_config.NumberColumn("Total"),
        "Assistant": st.column_config.NumberColumn("Assistant"),
        "Thinking": st.column_config.NumberColumn("Thinking"),
        "First prompt": st.column_config.TextColumn("First Prompt", width="large"),
    },
)
