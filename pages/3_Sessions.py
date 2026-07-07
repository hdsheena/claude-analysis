"""Page: Sessions - Session listing, drill-down, and raw data viewer."""

import streamlit as st

st.set_page_config(
    page_title="Sessions - Claude Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

import json
import pandas as pd
from datetime import datetime
from collections import Counter

from shared import load_sessions, apply_all_filters, render_sidebar
from claude_analyzer.stats import format_tokens
from claude_analyzer.search import build_tool_index, search_tool_calls, get_conversation_context, abbreviate_guids


st.title("🔍 Session Explorer & Raw Data Viewer")

# ── Sidebar & filters ────────────────────────────────────────────────────────

source, project_filter, time_range = render_sidebar()

# ── Load data ────────────────────────────────────────────────────────────────

sessions = load_sessions(source=source)
sessions = apply_all_filters(sessions, project_filter, time_range)

if not sessions:
    st.warning("No sessions match the filter.")
    st.stop()

# ── Tool search ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner="Indexing tool calls...")
def _build_search_index(_sessions):
    return build_tool_index(_sessions)

with st.expander("🔍 Search tool calls (Trello cards, tool names, etc.)", expanded=False):
    search_query = st.text_input(
        "Search by card name, tool, or keyword",
        placeholder="e.g. 'Order recommendations' or 'trello_create_card'",
        key="tool_search",
    )

    if search_query.strip():
        index = _build_search_index(sessions)
        results = search_tool_calls(index, search_query.strip())

        if not results:
            st.info(f"No tool calls matching '{search_query}' found.")
        else:
            st.caption(f"Found {len(results)} matching tool calls across "
                       f"{len(set(r['session_id'] for r in results))} sessions")

            # Build a compact dataframe
            rows = []
            for r in results[:100]:
                inp_preview = json.dumps(abbreviate_guids(r["tool_input"]))[:120]
                rows.append({
                    "Session": r["session_id"][:16] + "...",
                    "Full ID": r["session_id"],
                    "Project": r["project"],
                    "Tool": r["tool_name"][:40],
                    "Input": inp_preview,
                    "Msg #": r["message_idx"],
                    "User said": r["preceding_user_msg"][:120],
                })

            df_results = pd.DataFrame(rows)

            event_search = st.dataframe(
                df_results[["Session", "Project", "Tool", "Input", "User said"]],
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="tool_search_table",
                column_config={
                    "Session": st.column_config.TextColumn("Session", width="small"),
                    "Project": st.column_config.TextColumn("Project", width="medium"),
                    "Tool": st.column_config.TextColumn("Tool", width="medium"),
                    "Input": st.column_config.TextColumn("Input", width="large"),
                    "User said": st.column_config.TextColumn("User said", width="large"),
                },
            )

            # Show conversation context on click
            sel_rows = event_search.selection.get("rows", []) if event_search.selection else []
            if sel_rows and sel_rows[0] < len(df_results):
                row = df_results.iloc[sel_rows[0]]
                ctx = get_conversation_context(sessions, row["Full ID"], int(row["Msg #"]))
                if ctx:
                    st.divider()
                    st.subheader(f"💬 Conversation context — [{ctx['session'].project}]")
                    for m in ctx["messages"]:
                        is_highlight = m["idx"] == ctx["highlighted_idx"]
                        border = "2px solid #ab63fa" if is_highlight else "1px solid #2a2a4a"
                        with st.container(border=True):
                            role_label = "👤 User" if m["role"] == "user" else "🤖 Assistant"
                            prefix = "🔽" if is_highlight else "  "
                            st.caption(f"{prefix} {role_label} · msg #{m['idx']}")
                            if m["tools"]:
                                st.caption("🛠️ " + ", ".join(m["tools"][:6]))
                            if m["text"]:
                                st.markdown(m["text"][:2000])

    st.divider()

# ── Build session dataframe (cached) ─────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner="Building session list...")
def _build_session_df(_sessions):
    rows = []
    for s in _sessions:
        total_tokens = s.total_input_tokens + s.total_output_tokens
        started = None
        if s.started_at:
            try:
                started = datetime.fromtimestamp(
                    float(s.started_at) / 1000.0
                    if float(s.started_at) > 1e12
                    else float(s.started_at)
                )
            except (ValueError, TypeError):
                pass

        rows.append({
            "Session ID": s.session_id[:12],
            "Full ID": s.session_id,
            "Project": s.project,
            "Source": s.source,
            "Messages": len(s.messages),
            "Lines": s.line_count,
            "Token I/O": total_tokens,
            "Input Tokens": s.total_input_tokens,
            "Output Tokens": s.total_output_tokens,
            "Cache Read": s.total_cache_read,
            "Started": started,
            "First Message": (s.first_user_msg or "")[:100],
            "Kind": s.kind or "",
            "Name": s.name or "",
            "Filepath": s.filepath,
        })
    return pd.DataFrame(rows)

df_sessions = _build_session_df(sessions)

# ── Session table ────────────────────────────────────────────────────────────

st.subheader(f"📋 Sessions ({len(df_sessions)}) — {source.upper()}")

sort_col = st.selectbox(
    "Sort by",
    options=[
        "Messages",
        "Token I/O",
        "Input Tokens",
        "Output Tokens",
        "Lines",
        "Cache Read",
        "Started",
    ],
    index=0,
)

df_display = df_sessions.sort_values(sort_col, ascending=False).copy()
df_display["Tokens (fmt)"] = df_display["Token I/O"].apply(format_tokens)
df_display["Cache (fmt)"] = df_display["Cache Read"].apply(format_tokens)

event = st.dataframe(
    df_display[
        [
            "Session ID",
            "Project",
            "Source",
            "Messages",
            "Tokens (fmt)",
            "Cache (fmt)",
            "Started",
            "Kind",
            "First Message",
        ]
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Session ID": st.column_config.TextColumn("Session ID", width="small"),
        "Project": st.column_config.TextColumn("Project", width="medium"),
        "Source": st.column_config.TextColumn("Source", width="small"),
        "Messages": st.column_config.NumberColumn("Msgs", format="d"),
        "Tokens (fmt)": st.column_config.TextColumn("Tokens"),
        "Cache (fmt)": st.column_config.TextColumn("Cache"),
        "Started": st.column_config.DatetimeColumn("Started", format="YYYY-MM-DD HH:mm"),
        "Kind": st.column_config.TextColumn("Kind", width="small"),
        "First Message": st.column_config.TextColumn("First Message", width="large"),
    },
    on_select="rerun",
    selection_mode="single-row",
    key="session_table",
)

# ── Drill-down detail view ───────────────────────────────────────────────────

selected_rows = event.selection.get("rows", []) if event.selection else []

if selected_rows:
    row_idx = selected_rows[0]
    selected_row_data = (
        df_display.iloc[row_idx] if row_idx < len(df_display) else None
    )

    if selected_row_data is not None:
        selected_id = selected_row_data["Full ID"]
        sess = next(
            (s for s in sessions if s.session_id == selected_id), None
        )
        if sess:
            st.divider()
            st.subheader(f"📌 Session Detail: {sess.session_id[:16]}...")

            # Metrics row
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            with c1:
                st.metric("Messages", len(sess.messages))
            with c2:
                st.metric("Lines", sess.line_count)
            with c3:
                st.metric(
                    "Input Tokens",
                    format_tokens(sess.total_input_tokens),
                )
            with c4:
                st.metric(
                    "Output Tokens",
                    format_tokens(sess.total_output_tokens),
                )
            with c5:
                st.metric(
                    "Cache Read",
                    format_tokens(sess.total_cache_read),
                )
            with c6:
                st.metric(
                    "Cache Created",
                    format_tokens(sess.total_cache_create),
                )

            # Meta info
            st.caption(
                f"**Project:** {sess.project} • "
                f"**Source:** {sess.source} • "
                f"**File:** `{sess.filepath}`"
            )
            if sess.name:
                st.caption(f"**Name:** {sess.name}")
            if sess.cwd:
                st.caption(f"**CWD:** {sess.cwd}")

            # ── Model & tool breakdown ────────────────────────────────

            models = Counter()
            tools = Counter()

            for msg in sess.messages:
                if msg.msg_type == "assistant":
                    if msg.model:
                        models[msg.model] += 1
                    for tool in msg.tools_used:
                        tools[tool] += 1

            col_a, col_b = st.columns(2)

            with col_a:
                if models:
                    st.caption("**Models used:**")
                    df_models = pd.DataFrame(
                        [
                            {"Model": m.replace("claude-", ""), "Calls": c}
                            for m, c in models.most_common(10)
                        ]
                    )
                    st.dataframe(
                        df_models, hide_index=True, use_container_width=True
                    )

            with col_b:
                if tools:
                    st.caption("**Tools used:**")
                    df_tools = pd.DataFrame(
                        [
                            {"Tool": t, "Calls": c}
                            for t, c in tools.most_common(10)
                        ]
                    )
                    st.dataframe(
                        df_tools, hide_index=True, use_container_width=True
                    )

            # ── Messages: Chat View / Raw JSONL ─────────────────────────

            st.divider()
            tab_chat, tab_raw, tab_jsonl = st.tabs(
                ["💬 Chat View", "📝 Raw Messages (JSON)", "📄 Source JSONL"]
            )

            with tab_chat:
                _render_chat_view(sess)

            with tab_raw:
                raw_messages = []
                for msg in sess.messages:
                    raw_messages.append({
                        "type": msg.msg_type,
                        "model": msg.model,
                        "stop_reason": msg.stop_reason,
                        "input_tokens": msg.input_tokens,
                        "output_tokens": msg.output_tokens,
                        "cache_read": msg.cache_read_tokens,
                        "cache_create": msg.cache_create_tokens,
                        "tools_used": msg.tools_used,
                    })

                st.caption(
                    f"{len(raw_messages)} parsed messages "
                    f"(showing first 200)"
                )
                st.json(raw_messages[:200])

                if len(raw_messages) > 200:
                    st.info(
                        f"... and {len(raw_messages) - 200} more messages"
                    )

            with tab_jsonl:
                if sess.source == "mimo":
                    st.info(
                        "Mimo sessions are stored in a SQLite database "
                        f"(`{sess.filepath}`). "
                        "Switch to the Raw Messages tab for parsed message data."
                    )
                else:
                    st.caption(
                        f"Source: `{sess.filepath}` • "
                        f"{sess.line_count} lines"
                    )
                    try:
                        with open(sess.filepath, encoding="utf-8", errors="replace") as f:
                            raw_text = f.read()

                        max_chars = 100_000
                        total_chars = len(raw_text)
                        if total_chars > max_chars:
                            raw_text = raw_text[:max_chars]

                        st.code(raw_text, language="json", line_numbers=True)

                        if total_chars > max_chars:
                            st.info(
                                f"File truncated to first {max_chars:,} chars "
                                f"(total: {total_chars:,})"
                            )
                    except Exception as e:
                        st.error(f"Could not read file: {e}")

else:
    st.info("👆 Click a row in the session table above to see details, "
            "chat view, and raw JSONL data.")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_text_from_content(content) -> str:
    """Extract readable text from a message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "?")
                    tool_input = block.get("input", {})
                    input_str = json.dumps(tool_input)[:200]
                    texts.append(f"[tool_use: {tool_name}({input_str})]")
                elif block.get("type") == "tool_result":
                    texts.append("[tool_result]")
        return " ".join(texts)
    return str(content)


def _extract_text_from_freebuff_blocks(blocks) -> str:
    """Extract readable text from Freebuff-style blocks."""
    texts = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")
        if block_type in ("text", "reasoning"):
            texts.append(block.get("content", ""))
        elif block_type == "tool":
            tool_input = block.get("input", {})
            input_str = json.dumps(tool_input)[:200] if tool_input else ""
            texts.append(f"[tool: {block.get('content', '?')}({input_str})]")
        elif block_type == "mode-divider":
            texts.append("---")
    return "\n".join(texts)


def _render_chat_view(sess):
    """Render messages in a chat-like UI with actual message content."""
    max_show = 200
    st.caption(
        f"Showing {min(max_show, len(sess.messages))} of "
        f"{len(sess.messages)} messages"
    )

    for i, msg in enumerate(sess.messages[:max_show]):
        role = "user" if msg.msg_type == "user" else "assistant"

        with st.chat_message(role):
            # Metadata banner
            if msg.msg_type == "assistant":
                model_short = (
                    msg.model.replace("claude-", "") if msg.model else "?"
                )
                meta = (
                    f"🤖 {model_short} • "
                    f"in: {format_tokens(msg.input_tokens)} • "
                    f"out: {format_tokens(msg.output_tokens)} • "
                    f"stop: {msg.stop_reason}"
                )
                st.caption(meta)
                if msg.tools_used:
                    st.caption("🛠️ " + ", ".join(msg.tools_used[:10]))
            else:
                st.caption(f"👤 user message #{i + 1}")

            # Extract and show message content from _raw data
            raw = getattr(msg, "_raw", None)
            if raw:
                # Mimo format: content is in _parts
                parts = raw.get("_parts", [])
                if parts:
                    texts = []
                    for p in parts:
                        if not isinstance(p, dict):
                            continue
                        if p.get("type") == "text":
                            texts.append(p.get("text", ""))
                        elif p.get("type") == "tool":
                            tool_name = p.get("tool", "?")
                            state = p.get("state", {})
                            title = state.get("title", "") if isinstance(state, dict) else ""
                            texts.append(f"[tool: {tool_name}] {title}")
                        elif p.get("type") == "reasoning":
                            texts.append(f"[reasoning] {p.get('text', '')[:200]}")
                    if texts:
                        st.markdown("\n".join(texts)[:3000])
                else:
                    # Claude/Freebuff format
                    inner = raw.get("message", raw)
                    content = inner.get("content", "")
                    blocks = inner.get("blocks", [])
                    if blocks and not content:
                        # Freebuff: text is in blocks
                        text = _extract_text_from_freebuff_blocks(blocks)
                    else:
                        text = _extract_text_from_content(content)
                    if text.strip():
                        st.markdown(text[:3000])

    if len(sess.messages) > max_show:
        st.info(
            f"... and {len(sess.messages) - max_show} more messages "
            f"(switch to Raw JSONL tab for full data)"
        )
