"""OpenAI Codex session parser.

Reads the Codex thread index at ~/.codex/state_5.sqlite (threads table).
Each thread carries the authoritative usage data: model, tokens_used, cwd,
title, first_user_message, and timestamps. The per-thread rollout transcripts
are stored as jsonl files (rollout_path); their file sizes are counted as real
disk usage.

tokens_used is the session-wide total with no input/output split, so it is
attributed to a single synthetic assistant message as input tokens. Cost is
therefore an overestimate per token — a consistent relative signal only.
"""

import json
import os
import sqlite3

from .parser import Session, Message, normalize_project_name

CODEX_DB_PATH = os.path.expanduser("~/.codex/state_5.sqlite")


def parse_codex_sessions() -> list:
    """Parse Codex threads from ~/.codex/state_5.sqlite."""
    sessions = []

    if not os.path.isfile(CODEX_DB_PATH):
        return sessions

    try:
        conn = sqlite3.connect(CODEX_DB_PATH)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return sessions

    try:
        rows = conn.execute(
            """SELECT id, rollout_path, created_at, cwd, title, tokens_used,
                      model, first_user_message, preview, name, git_branch
               FROM threads"""
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        rollout_path = row["rollout_path"]
        proj_name = normalize_project_name(
            os.path.basename((row["cwd"] or "").rstrip("/")) or "unknown"
        )

        sess = Session(
            session_id=row["id"],
            source="codex",
            project=proj_name,
            filepath=rollout_path,
            size_bytes=os.path.getsize(rollout_path) if os.path.isfile(rollout_path) else 0,
        )
        sess.name = (row["title"] or row["name"] or "")[:300]
        sess.kind = "codex"
        sess.cwd = row["cwd"]
        sess.started_at = row["created_at"] or 0
        sess._branch = row["git_branch"]
        sess.first_user_msg = (row["first_user_message"] or row["preview"] or "")[:300]

        tokens = row["tokens_used"] or 0
        sess.messages.append(Message(
            msg_type="assistant",
            model=row["model"],
            input_tokens=tokens,
        ))
        sess.line_count = 1

        sessions.append(sess)

    return sessions
