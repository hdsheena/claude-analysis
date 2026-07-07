"""Antigravity session parser."""

import json
import os

from .parser import Session, Message, _parse_iso_to_epoch, normalize_project_name


ANTIGRAVITY_BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")


def parse_antigravity_sessions() -> list:
    """Parse Antigravity sessions from ~/.gemini/antigravity/brain/ transcript files.

    Each brain directory (UUID-named) contains a .system_generated/logs/transcript.jsonl
    with conversation steps. No per-message token counts or model identifiers are
    available in the transcript format, so token/cost fields will be 0.
    """
    sessions = []

    if not os.path.isdir(ANTIGRAVITY_BRAIN_DIR):
        return sessions

    for brain_dir in sorted(os.listdir(ANTIGRAVITY_BRAIN_DIR)):
        brain_path = os.path.join(ANTIGRAVITY_BRAIN_DIR, brain_dir)
        if not os.path.isdir(brain_path):
            continue

        transcript_path = os.path.join(
            brain_path, ".system_generated", "logs", "transcript.jsonl"
        )
        if not os.path.isfile(transcript_path):
            continue

        session_id = brain_dir

        # Try to extract project name from metadata files in the brain dir
        project = "antigravity"
        for fname in sorted(os.listdir(brain_path)):
            fpath = os.path.join(brain_path, fname)
            if not os.path.isfile(fpath):
                continue
            name, ext = os.path.splitext(fname)
            if ext in (".md", ".json") and name not in (
                "implementation_plan", "task", "walkthrough",
            ):
                project = normalize_project_name(name)
                break

        sess = Session(
            session_id=session_id,
            source="antigravity",
            project=project,
            filepath=transcript_path,
        )

        try:
            with open(transcript_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            continue

        sess.line_count = len(lines)

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_source = d.get("source", "")

            # Map Antigravity source to msg_type
            if entry_source == "MODEL":
                msg_type = "assistant"
            elif entry_source == "USER_EXPLICIT":
                msg_type = "user"
            else:
                continue  # Skip system/internal entries

            msg = Message(msg_type=msg_type)
            msg._raw = d

            # Extract tool names from tool_calls
            tool_calls = d.get("tool_calls", [])
            if isinstance(tool_calls, list):
                msg.tools_used = [
                    tc.get("name", "?")
                    for tc in tool_calls
                    if isinstance(tc, dict)
                ]

            sess.messages.append(msg)

            # Set timestamp from first entry
            if sess.started_at is None:
                sess.started_at = _parse_iso_to_epoch(d.get("created_at", ""))

            # Capture first user message
            if msg_type == "user" and sess.first_user_msg is None:
                content = d.get("content", "")
                if isinstance(content, str):
                    sess.first_user_msg = content[:300]

        # Fallback timestamp from file mtime
        if sess.started_at is None:
            try:
                sess.started_at = int(os.path.getmtime(transcript_path))
            except OSError:
                pass

        sessions.append(sess)

    return sessions
