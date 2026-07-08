"""Search Claude sessions for tool calls, Trello cards, and conversation context.

Usage:
    from claude_analyzer.search import find_sessions_by_card, build_tool_index, search_tool_calls

    sessions = parse_sessions("all")
    index = build_tool_index(sessions)

    # Find sessions where a Trello card was created/modified
    matches = find_sessions_by_card(index, "Order recommendations with null")

    # Search all tool calls
    results = search_tool_calls(index, "trello_create_card")

    # Get conversation context around a specific tool call
    context = get_conversation_context(sessions, session_id, message_index)
"""

import re
import json
from collections import defaultdict
from typing import Optional

from .parser import Session, Message


def abbreviate_guids(obj, max_len: int = 8):
    """Recursively abbreviate long hex/UUID strings in dicts, lists, and strings.

    Hex strings longer than max_len get truncated to prefix...
    e.g. '67e57b7ec17def66f7dfef16' -> '67e57b7e...'
    """
    return _abbreviate_guids(obj, max_len)


def _abbreviate_guids(obj, max_len: int = 8):
    """Recursive helper for abbreviate_guids."""
    if isinstance(obj, dict):
        return {k: _abbreviate_guids(v, max_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_abbreviate_guids(item, max_len) for item in obj]
    if isinstance(obj, str):
        if re.fullmatch(r"[0-9a-fA-F-]{" + str(max_len + 1) + r",}", obj):
            return obj[:max_len] + "..."
        return obj
    return obj
    if isinstance(obj, dict):
        return {k: abbreviate_guids(v, max_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [abbreviate_guids(item, max_len) for item in obj]
    if isinstance(obj, str):
        # Abbreviate hex strings (with or without dashes, e.g. UUIDs)
        if re.fullmatch(r"[0-9a-fA-F-]{" + str(max_len + 1) + r",}", obj):
            return obj[:max_len] + "..."
        return obj
    return obj


def build_tool_index(sessions: list) -> list:
    """Build a searchable index of all tool_use calls across sessions.

    Returns a list of dicts, each with:
        session_id, project, source, first_user_msg, message_idx,
        tool_name, tool_input (dict), preceding_user_msg
    """
    index = []

    for sess in sessions:
        for i, msg in enumerate(sess.messages):
            tools = _extract_tool_calls(msg)
            for tool in tools:
                # Find the most recent preceding user message for context
                user_msg = _find_preceding_user(sess.messages, i)

                index.append({
                    "session_id": sess.session_id,
                    "project": sess.project,
                    "source": sess.source,
                    "first_user_msg": (sess.first_user_msg or "")[:200],
                    "message_idx": i,
                    "tool_name": tool["name"],
                    "tool_input": tool["input"],
                    "preceding_user_msg": user_msg,
                })

    return index


def _extract_tool_calls(msg: Message) -> list:
    """Extract tool_use blocks from a message's raw data."""
    tools = []

    raw = getattr(msg, "_raw", None)
    if not raw:
        return tools

    # Claude format: message.content[] has tool_use blocks
    inner = raw.get("message", {})
    content = inner.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools.append({
                    "name": block.get("name", "?"),
                    "input": block.get("input", {}),
                })

    # Mimo/Opencode format: _parts[] has tool parts
    parts = raw.get("_parts", [])
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "tool":
            tools.append({
                "name": p.get("tool", "?"),
                "input": p.get("state", p.get("input", {})),
            })

    return tools


def _find_preceding_user(messages: list, idx: int) -> str:
    """Find the most recent user message before the given index."""
    for j in range(idx - 1, -1, -1):
        if messages[j].msg_type == "user":
            raw = getattr(messages[j], "_raw", None)
            if raw:
                # Claude format
                inner = raw.get("message", {})
                content = inner.get("content", "")
                if isinstance(content, str):
                    return content[:300]
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            return block.get("text", "")[:300]
                # Mimo/Opencode format
                parts = raw.get("_parts", [])
                for p in parts:
                    if isinstance(p, dict) and p.get("type") == "text":
                        return p.get("text", "")[:300]
            break
    return ""


def search_tool_calls(index: list, query: str) -> list:
    """Search tool calls by tool name, input params, or preceding user message.

    Case-insensitive substring match. Returns matching index entries, most recent first.
    """
    query_lower = query.lower()
    results = []

    for entry in index:
        # Search in tool name
        if query_lower in entry["tool_name"].lower():
            results.append(entry)
            continue

        # Search in tool input (serialize to string)
        input_str = json.dumps(entry["tool_input"]).lower()
        if query_lower in input_str:
            results.append(entry)
            continue

        # Search in the preceding user message
        if query_lower in entry["preceding_user_msg"].lower():
            results.append(entry)
            continue

        # Search in first user message of the session
        if query_lower in (entry["first_user_msg"] or "").lower():
            results.append(entry)
            continue

    # Sort by project/session for readability
    results.sort(key=lambda r: (r["project"], r["session_id"]), reverse=True)
    return results


def find_sessions_by_card(index: list, card_name: str) -> list:
    """Find sessions where a Trello card matching the name was created/updated.

    Searches tool_use inputs for Trello-related tools where the card name
    or description contains the given string. Returns unique sessions.
    """
    query_lower = card_name.lower()
    seen = {}
    results = []

    for entry in index:
        name = entry["tool_name"]
        if "trello" not in name.lower():
            continue

        # Search for the card name in the tool input
        input_str = json.dumps(entry["tool_input"]).lower()
        if query_lower not in input_str:
            continue

        sid = entry["session_id"]
        if sid in seen:
            seen[sid]["tool_calls"].append(entry)
        else:
            seen[sid] = {
                "session_id": sid,
                "project": entry["project"],
                "source": entry["source"],
                "first_user_msg": entry["first_user_msg"],
                "tool_calls": [entry],
            }

    return sorted(seen.values(), key=lambda r: len(r["tool_calls"]), reverse=True)


def get_conversation_context(
    sessions: list, session_id: str, message_idx: int, context: int = 5
) -> Optional[dict]:
    """Get conversation context around a specific message in a session.

    Returns a dict with:
        session (Session), messages (list of dicts with role and text),
        highlighted_idx (the index within the returned slice)
    """
    sess = next((s for s in sessions if s.session_id == session_id), None)
    if not sess:
        return None

    start = max(0, message_idx - context)
    end = min(len(sess.messages), message_idx + context + 1)

    messages = []
    for i in range(start, end):
        msg = sess.messages[i]
        text = _extract_message_text(msg)
        messages.append({
            "idx": i,
            "role": "user" if msg.msg_type == "user" else "assistant",
            "type": msg.msg_type,
            "model": msg.model or "",
            "tools": msg.tools_used,
            "text": text,
        })

    return {
        "session": sess,
        "messages": messages,
        "highlighted_idx": message_idx - start,
    }


def _extract_message_text(msg: Message) -> str:
    """Extract readable text from a message."""
    raw = getattr(msg, "_raw", None)
    if not raw:
        return ""

    # Claude format
    inner = raw.get("message", {})
    content = inner.get("content", "")
    if isinstance(content, str):
        return content[:500]
    if isinstance(content, list):
        texts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                texts.append(block.get("text", ""))
            elif btype == "tool_use":
                texts.append(f"[tool: {block.get('name', '?')}]")
            elif btype == "tool_result":
                texts.append("[tool_result]")
        return " ".join(texts)[:500]

    # Mimo/Opencode format
    parts = raw.get("_parts", [])
    texts = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            texts.append(p.get("text", ""))
        elif p.get("type") == "tool":
            texts.append(f"[tool: {p.get('tool', '?')}]")
        elif p.get("type") == "reasoning":
            texts.append(f"[reasoning: {p.get('text', '')[:200]}]")
    return "\n".join(texts)[:500]


def search_report(index: list, query: str, max_results: int = 20) -> str:
    """Generate a text report from a tool call search."""
    results = search_tool_calls(index, query)[:max_results]

    if not results:
        return f"No tool calls matching '{query}' found."

    lines = []
    lines.append(f"\n┌─ TOOL SEARCH: '{query}' — {len(results)} matches ─┐")

    # Group by session
    by_session = defaultdict(list)
    for r in results:
        by_session[r["session_id"]].append(r)

    for sid, entries in sorted(by_session.items()):
        first = entries[0]
        lines.append(f"\n  📁 [{first['project']}] {sid[:20]}...")
        lines.append(f"     First msg: {first['first_user_msg'][:120]}")
        for e in entries[:5]:
            inp_preview = json.dumps(abbreviate_guids(e["tool_input"]))[:120]
            lines.append(f"     🛠️  {e['tool_name']}  →  {inp_preview}")
        if len(entries) > 5:
            lines.append(f"     ... and {len(entries) - 5} more tool calls")

    return "\n".join(lines)


def card_report(index: list, card_name: str) -> str:
    """Generate a text report for sessions involving a Trello card."""
    sessions = find_sessions_by_card(index, card_name)

    if not sessions:
        return f"No sessions found involving Trello card '{card_name}'."

    lines = []
    lines.append(f"\n┌─ TRELLO CARD: '{card_name}' — {len(sessions)} sessions ─┐")

    for s in sessions:
        lines.append(f"\n  📁 [{s['project']}] {s['session_id'][:20]}...")
        lines.append(f"     First msg: {s['first_user_msg'][:150]}")
        for tc in s["tool_calls"][:8]:
            inp = tc["tool_input"]
            card = inp.get("name", inp.get("card_name", inp.get("title", "?")))
            action = tc["tool_name"].replace("mcp__trello__trello_", "")
            lines.append(f"     🃏 {action}: {card}")
            if tc["preceding_user_msg"]:
                lines.append(f"        ↳ user said: {tc['preceding_user_msg'][:120]}")
        if len(s["tool_calls"]) > 8:
            lines.append(f"     ... and {len(s['tool_calls']) - 8} more tool calls")

    return "\n".join(lines)
