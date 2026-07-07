"""Freebuff/Codebuff session parser."""

import json
import os
import glob

from .parser import Session, Message, normalize_project_name


def _project_name_from_freebuff_path(filepath: str) -> str:
    """Extract project name from a freebuff project directory path."""
    # ~/.config/manicode/projects/repo-sync-tools/chats/... -> repo-sync-tools
    parts = filepath.split(os.sep)
    try:
        projects_idx = parts.index("projects")
        if projects_idx + 1 < len(parts):
            return normalize_project_name(parts[projects_idx + 1])
    except ValueError:
        pass
    return "unknown"


def parse_freebuff_sessions() -> list:
    """Parse Freebuff/Codebuff sessions from ~/.config/manicode/projects."""
    FREE_BUFF_PROJECTS_DIR = os.path.expanduser("~/.config/manicode/projects")
    sessions = []

    if not os.path.isdir(FREE_BUFF_PROJECTS_DIR):
        return sessions

    # Find all chat-messages.json files
    chat_files = glob.glob(
        os.path.join(FREE_BUFF_PROJECTS_DIR, "*", "chats", "*", "chat-messages.json")
    )

    for chat_file in chat_files:
        try:
            with open(chat_file, encoding="utf-8") as f:
                messages_raw = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        if not isinstance(messages_raw, list) or not messages_raw:
            continue

        # Derive session ID from path: .../projects/<proj>/chats/<timestamp>/chat-messages.json
        chat_dir = os.path.dirname(chat_file)
        session_id = os.path.basename(chat_dir)
        project = _project_name_from_freebuff_path(chat_file)

        sess = Session(
            session_id=session_id,
            source="freebuff",
            project=project,
            filepath=chat_file,
            line_count=len(messages_raw),
        )

        # Parse messages
        for raw_msg in messages_raw:
            variant = raw_msg.get("variant", "?")

            if variant == "user":
                msg_type = "user"
            elif variant == "ai":
                msg_type = "assistant"
            else:
                msg_type = variant

            msg = Message(msg_type=msg_type)
            msg._raw = raw_msg

            # Extract content from blocks or top-level content
            blocks = raw_msg.get("blocks", [])
            tools = []
            if variant == "ai" and blocks:
                for block in blocks:
                    if isinstance(block, dict):
                        block_type = block.get("type", "")
                        if block_type == "tool":
                            tools.append(block.get("content", "?"))

            msg.tools_used = tools

            # Timestamp: use the chat directory name or file mtime
            if sess.started_at is None:
                try:
                    sess.started_at = int(os.path.getmtime(chat_file))
                except OSError:
                    pass

            sess.messages.append(msg)

            # Capture first user message
            if variant == "user" and sess.first_user_msg is None:
                content = raw_msg.get("content", "")
                if not content and blocks:
                    for block in blocks:
                        if isinstance(block, dict) and block.get("type") == "text":
                            content = block.get("content", "")
                            break
                sess.first_user_msg = (content or "")[:300]

        # Read chat-meta.json for extra metadata
        meta_file = os.path.join(chat_dir, "chat-meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
                sess.name = meta.get("firstPrompt", "")[:100]
            except (json.JSONDecodeError, IOError):
                pass

        sessions.append(sess)

    return sessions
