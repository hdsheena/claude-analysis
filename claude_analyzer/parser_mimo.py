"""Mimo session parser."""

import json
import os
import sqlite3
from collections import defaultdict

from .parser import Session, Message, _parse_parts, normalize_project_name


MIMO_DB_PATH = os.path.expanduser("~/.local/share/mimocode/mimocode.db")


def parse_mimo_sessions() -> list:
    """Parse Mimo sessions from SQLite database at ~/.local/share/mimocode/."""
    sessions = []

    if not os.path.isfile(MIMO_DB_PATH):
        return sessions

    try:
        conn = sqlite3.connect(MIMO_DB_PATH)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return sessions

    try:
        # Load projects for directory mapping
        projects = {}
        for row in conn.execute("SELECT id, worktree, vcs FROM project"):
            projects[row["id"]] = {
                "worktree": row["worktree"] or "",
                "vcs": row["vcs"] or "",
            }

        # Load sessions
        session_rows = conn.execute(
            """SELECT id, project_id, slug, title, directory, time_created,
                      time_updated, summary_additions, summary_deletions,
                      summary_files, summary_diffs
               FROM session
               ORDER BY time_created"""
        ).fetchall()

        for srow in session_rows:
            sid = srow["id"]
            proj_info = projects.get(srow["project_id"], {})
            worktree = proj_info.get("worktree", srow["directory"] or "")
            proj_name = normalize_project_name(os.path.basename(worktree.rstrip("/")) if worktree else "unknown")

            sess = Session(
                session_id=sid,
                source="mimo",
                project=proj_name,
                filepath=MIMO_DB_PATH,
            )
            sess.name = srow["title"] or ""
            sess.kind = "mimo"
            sess.cwd = worktree
            if srow["time_created"]:
                sess.started_at = srow["time_created"]

            # Load messages for this session
            msg_rows = conn.execute(
                "SELECT id, agent_id, data FROM message WHERE session_id = ? ORDER BY time_created",
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
                model_info = mdata.get("model", {})
                if isinstance(model_info, dict):
                    msg.model = model_info.get("modelID", "") or ""

                # Extract token data
                tok = mdata.get("tokens", {})
                if isinstance(tok, dict):
                    msg.input_tokens = tok.get("input", 0) or 0
                    msg.output_tokens = tok.get("output", 0) or 0
                    cache = tok.get("cache", {})
                    if isinstance(cache, dict):
                        msg.cache_read_tokens = cache.get("read", 0) or 0
                        msg.cache_write_tokens = cache.get("write", 0) or 0

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

            sess.line_count = len(sess.messages)
            sessions.append(sess)

    finally:
        conn.close()

    return sessions
