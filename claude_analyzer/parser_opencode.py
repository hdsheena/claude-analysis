"""Opencode session parser."""

import json
import os
import sqlite3
from collections import defaultdict

from .parser import Session, Message, _parse_parts, normalize_project_name


OPENCODE_DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")


def parse_opencode_sessions() -> list:
    """Parse Opencode sessions from SQLite database at ~/.local/share/opencode/."""
    sessions = []

    if not os.path.isfile(OPENCODE_DB_PATH):
        return sessions

    try:
        conn = sqlite3.connect(OPENCODE_DB_PATH)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return sessions

    try:
        # Load workspaces for directory mapping
        workspaces = {}
        for row in conn.execute("SELECT id, directory FROM workspace"):
            workspaces[row["id"]] = row["directory"] or ""

        # Load sessions with pre-computed token columns
        session_rows = conn.execute(
            """SELECT id, slug, title, directory, workspace_id, agent, model,
                      tokens_input, tokens_output, tokens_cache_read, tokens_cache_write,
                      time_created, time_updated
               FROM session
               ORDER BY time_created"""
        ).fetchall()

        for srow in session_rows:
            sid = srow["id"]
            workdir = workspaces.get(srow["workspace_id"], srow["directory"] or "")
            proj_name = normalize_project_name(os.path.basename(workdir.rstrip("/")) if workdir else "unknown")

            sess = Session(
                session_id=sid,
                source="opencode",
                project=proj_name,
                filepath=OPENCODE_DB_PATH,
            )
            sess.name = srow["title"] or srow["slug"] or ""
            sess.kind = srow["agent"] or "opencode"
            sess.cwd = workdir
            if srow["time_created"]:
                sess.started_at = srow["time_created"]

            # Pre-computed token totals
            pre_input = srow["tokens_input"] or 0
            pre_output = srow["tokens_output"] or 0
            pre_cache_read = srow["tokens_cache_read"] or 0
            pre_cache_write = srow["tokens_cache_write"] or 0

            # Load messages
            msg_rows = conn.execute(
                "SELECT id, data, time_created FROM message WHERE session_id = ? ORDER BY time_created",
                (sid,),
            ).fetchall()

            msg_ids = [m["id"] for m in msg_rows]

            # Load parts and group by message_id
            parts_by_msg = defaultdict(list)
            if msg_ids:
                placeholders = ",".join("?" for _ in msg_ids)
                part_rows = conn.execute(
                    f"SELECT message_id, data FROM part WHERE message_id IN ({placeholders}) ORDER BY time_created",
                    msg_ids,
                ).fetchall()
                for prow in part_rows:
                    parts_by_msg[prow["message_id"]].append(prow["data"])

            # Build Message objects
            tokens_assigned = 0
            for mrow in msg_rows:
                try:
                    mdata = json.loads(mrow["data"]) if isinstance(mrow["data"], str) else (mrow["data"] or {})
                except json.JSONDecodeError:
                    mdata = {}

                role = mdata.get("role", "?")
                msg_type = "assistant" if role == "assistant" else ("user" if role == "user" else role)
                msg = Message(msg_type=msg_type)
                msg._raw = mdata

                # Model info
                msg.model = mdata.get("modelID", "") or ""
                if not msg.model:
                    model_info = mdata.get("model", {})
                    if isinstance(model_info, dict):
                        msg.model = model_info.get("modelID", "") or ""

                # Extract message-level token data
                tok = mdata.get("tokens", {})
                if isinstance(tok, dict):
                    msg.input_tokens = tok.get("input", 0) or 0
                    msg.output_tokens = tok.get("output", 0) or 0
                    msg.cache_read_tokens = tok.get("cache_read", 0) or 0
                    msg.cache_create_tokens = tok.get("cache_write", 0) or 0
                    tokens_assigned += msg.input_tokens + msg.output_tokens

                # Parts: extract tools and stash for chat view
                parts = parts_by_msg.get(mrow["id"], [])
                tools, parsed_parts = _parse_parts(parts)
                msg.tools_used = tools
                msg._raw["_parts"] = parsed_parts

                sess.messages.append(msg)

                # Capture first user message from text parts
                if role == "user" and sess.first_user_msg is None:
                    for pdata in parsed_parts:
                        if pdata.get("type") == "text":
                            sess.first_user_msg = (pdata.get("text", "") or "")[:300]
                            break

            # Fallback: use session-level pre-computed totals
            if tokens_assigned == 0 and sess.messages:
                assistant_msgs = [m for m in sess.messages if m.msg_type == "assistant"]
                if assistant_msgs:
                    first = assistant_msgs[0]
                    first.input_tokens = pre_input
                    first.output_tokens = pre_output
                    first.cache_read_tokens = pre_cache_read
                    first.cache_create_tokens = pre_cache_write
                else:
                    msg = Message(msg_type="assistant")
                    msg.model = srow["model"] or ""
                    msg.input_tokens = pre_input
                    msg.output_tokens = pre_output
                    msg.cache_read_tokens = pre_cache_read
                    msg.cache_create_tokens = pre_cache_write
                    sess.messages.append(msg)

            sess.line_count = len(sess.messages)
            sessions.append(sess)

    finally:
        conn.close()

    return sessions
