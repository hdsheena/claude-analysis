"""GitHub Copilot session parser.

Reads the Copilot CLI/extension session store at ~/.copilot/session-store.db.
Conversation content comes from the sessions + turns tables; per-turn token
and metered-usage data comes from assistant_usage_events (model, input/output/
cache/reasoning tokens, and total_nano_aiu — Copilot's "AI usage unit" meter).

Usage events are sparsely recorded (recording started ~mid-2026), so most
turns carry conversation text but no token data. That's expected; the parser
attaches tokens whenever a matching event exists.
"""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime

from .parser import Session, Message, normalize_project_name

COPILOT_DB_PATH = os.path.expanduser("~/.copilot/session-store.db")


def _to_epoch(ts: str) -> int:
    """Parse a Copilot timestamp (ISO 8601 or 'YYYY-MM-DD HH:MM:SS') to epoch."""
    if not ts:
        return 0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return 0


def parse_copilot_sessions() -> list:
    """Parse Copilot sessions from ~/.copilot/session-store.db."""
    sessions = []

    if not os.path.isfile(COPILOT_DB_PATH):
        return sessions

    try:
        conn = sqlite3.connect(COPILOT_DB_PATH)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return sessions

    try:
        usage_by_turn = defaultdict(list)
        for row in conn.execute(
            """SELECT session_id, turn_index, model, input_tokens, output_tokens,
                      cache_read_tokens, cache_write_tokens, reasoning_tokens,
                      total_nano_aiu, created_at
               FROM assistant_usage_events"""
        ):
            usage_by_turn[(row["session_id"], row["turn_index"])].append(row)

        for srow in conn.execute(
            """SELECT id, cwd, repository, branch, summary, created_at, updated_at
               FROM sessions
               ORDER BY created_at"""
        ):
            sid = srow["id"]
            worktree = srow["cwd"] or srow["repository"] or ""
            proj_name = normalize_project_name(os.path.basename(worktree.rstrip("/")) if worktree else "unknown")

            sess = Session(
                session_id=sid,
                source="copilot",
                project=proj_name,
                filepath=COPILOT_DB_PATH,
                size_bytes=0,
            )
            sess.name = (srow["summary"] or "")[:300] or ""
            sess.kind = "copilot"
            sess.cwd = srow["cwd"]
            sess.started_at = _to_epoch(srow["created_at"])
            sess._branch = srow["branch"]

            turn_rows = conn.execute(
                "SELECT turn_index, user_message, assistant_response, timestamp FROM turns WHERE session_id = ? ORDER BY turn_index",
                (sid,),
            ).fetchall()

            session_usage = []
            for trow in turn_rows:
                events = usage_by_turn.get((sid, trow["turn_index"]), [])
                user_text = (trow["user_message"] or "").strip()
                asst_text = (trow["assistant_response"] or "").strip()

                if user_text:
                    sess.messages.append(Message(msg_type="user"))
                    if sess.first_user_msg is None:
                        sess.first_user_msg = user_text[:300]

                if events:
                    tokens = _sum_usage(events)
                    latest = max(events, key=lambda e: _to_epoch(e["created_at"]))
                    sess.messages.append(Message(
                        msg_type="assistant",
                        model=latest["model"],
                        input_tokens=tokens["input"],
                        output_tokens=tokens["output"],
                        cache_read_tokens=tokens["cache_read"],
                        cache_create_tokens=tokens["cache_write"],
                    ))
                    session_usage.append({
                        "turn_index": trow["turn_index"],
                        "model": latest["model"],
                        "tokens": tokens,
                        "total_nano_aiu": sum(e["total_nano_aiu"] or 0 for e in events),
                        "created_at": _to_epoch(latest["created_at"]),
                    })
                elif asst_text:
                    sess.messages.append(Message(msg_type="assistant"))

            sess.line_count = len(turn_rows)
            sess._usage_events = session_usage
            sessions.append(sess)

    finally:
        conn.close()

    return sessions


def _sum_usage(events) -> dict:
    """Aggregate token counts across multiple usage events for one turn."""
    return {
        "input": sum(e["input_tokens"] or 0 for e in events),
        "output": sum(e["output_tokens"] or 0 for e in events),
        "cache_read": sum(e["cache_read_tokens"] or 0 for e in events),
        "cache_write": sum(e["cache_write_tokens"] or 0 for e in events),
        "reasoning": sum(e["reasoning_tokens"] or 0 for e in events),
    }
