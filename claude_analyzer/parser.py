"""Parse Claude session data from .claude directories, plus Freebuff, Mimo, Opencode, and Antigravity."""

import re
import json
import os
import sys
import glob
import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

# --- Configurable paths ---
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
LOCAL_AGENT_DIR = os.path.expanduser(
    "~/Library/Application Support/Claude/local-agent-mode-sessions"
)
SESSIONS_DIR = os.path.expanduser("~/.claude/sessions")

# Freebuff / Codebuff
FREE_BUFF_PROJECTS_DIR = os.path.expanduser("~/.config/manicode/projects")

# Mimo
MIMO_DB_PATH = os.path.expanduser("~/.local/share/mimocode/mimocode.db")

# Opencode
OPENCODE_DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")

# Antigravity
ANTIGRAVITY_BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")


@dataclass
class Message:
    """A single message in a session."""
    msg_type: str
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    tools_used: list = field(default_factory=list)


@dataclass
class Session:
    """One Claude session."""
    session_id: str
    source: str  # "projects" or "local-agent"
    project: str
    filepath: str
    line_count: int = 0
    messages: list = field(default_factory=list)
    first_user_msg: Optional[str] = None
    # From registry
    name: Optional[str] = None
    kind: Optional[str] = None
    cwd: Optional[str] = None
    started_at: Optional[int] = None

    @property
    def total_input_tokens(self) -> int:
        return sum(m.input_tokens for m in self.messages)

    @property
    def total_output_tokens(self) -> int:
        return sum(m.output_tokens for m in self.messages)

    @property
    def total_cache_read(self) -> int:
        return sum(m.cache_read_tokens for m in self.messages)

    @property
    def total_cache_create(self) -> int:
        return sum(m.cache_create_tokens for m in self.messages)


def parse_message(line: str) -> Optional[Message]:
    """Parse one JSONL line into a Message."""
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return None

    msg_type = d.get("type", "?")
    msg = Message(msg_type=msg_type)
    msg._raw = d  # store for first-user-message reuse

    if msg_type == "assistant":
        inner = d.get("message", {})
        msg.model = inner.get("model")
        msg.stop_reason = inner.get("stop_reason")
        usage = inner.get("usage", {})
        msg.input_tokens = usage.get("input_tokens", 0)
        msg.output_tokens = usage.get("output_tokens", 0)
        msg.cache_read_tokens = usage.get("cache_read_input_tokens", 0)
        msg.cache_create_tokens = usage.get("cache_creation_input_tokens", 0)
        # Extract tool_use names
        content = inner.get("content", [])
        if isinstance(content, list):
            msg.tools_used = [
                b.get("name", "?")
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
    elif msg_type == "user":
        inner = d.get("message", {})
        msg.model = inner.get("model")

    return msg


def _parse_iso_to_epoch(ts_str: str) -> Optional[int]:
    """Parse an ISO 8601 timestamp string to epoch seconds."""
    if not ts_str:
        return None
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def _find_jsonl_files(root: str) -> list:
    """Recursively find all .jsonl files under root."""
    if not os.path.isdir(root):
        return []
    return glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)


def normalize_project_name(name: str) -> str:
    """Normalize a project name for consistent comparison across sources.

    Replaces hyphens/underscores with spaces, strips leading dots/slashes,
    collapses whitespace, removes duplicate consecutive words,
    and strips date/timestamp suffixes. Preserves original casing.
    """
    if not name:
        return "unknown"
    name = name.strip().lstrip("./-_")
    name = name.replace("-", " ").replace("_", " ")
    name = " ".join(name.split())
    if not name:
        return "unknown"

    # Remove duplicate consecutive words (e.g. "screenpipe screenpipe main")
    words = name.split()
    deduped = []
    for w in words:
        if not deduped or w.lower() != deduped[-1].lower():
            deduped.append(w)
    name = " ".join(deduped)

    # Strip date/timestamp suffixes like "20260624T1645" or "20260624"
    name = re.sub(r"\s+\d{8,}(T\d{4,})?$", "", name)

    # Strip run numbers like "run 11" from the end
    name = re.sub(r"\s+run\s+\d+$", "", name, flags=re.IGNORECASE)

    name = name.strip()
    return name or "unknown"


def project_name_from_path(filepath: str, source: str) -> str:
    """Extract a human-readable project name from the filepath."""
    parts = filepath.replace(os.path.expanduser("~"), "").split(os.sep)
    # ~/.claude/projects/-Users-m4mbp-GitHub-evc/uuid.jsonl  ->  evc
    # ~/Library/.../local-agent-mode-sessions/uuid/uuid.jsonl ->  local-agent
    if source == "projects":
        for p in parts:
            if p.startswith("-Users-"):
                # Simplify: strip the common prefix
                short = p.replace("-Users-m4mbp-", "").replace("-Users-m4mbp", "")
                short = short.replace("GitHub-", "").replace("Documents-GitHub-", "")
                # Normalize
                short = normalize_project_name(short)
                # Truncate long names
                if len(short) > 50:
                    short = short[:47] + "..."
                return short
        return "unknown"
    else:
        return "local-agent"


# ═══════════════════════════════════════════════════════════════════════════════
# Freebuff / Codebuff parser
# ═══════════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════════
# Mimo parser
# ═══════════════════════════════════════════════════════════════════════════════


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

            # Build message ID lookup for parts
            msg_ids = [m["id"] for m in msg_rows]
            msg_index = {m["id"]: i for i, m in enumerate(msg_rows)}

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

                # Extract token data (same keys as Opencode: tokens.input/output/cache)
                tok = mdata.get("tokens", {})
                if isinstance(tok, dict):
                    msg.input_tokens = tok.get("input", 0) or 0
                    msg.output_tokens = tok.get("output", 0) or 0
                    cache = tok.get("cache", {})
                    if isinstance(cache, dict):
                        msg.cache_read_tokens = cache.get("read", 0) or 0
                        msg.cache_write_tokens = cache.get("write", 0) or 0

                # Parts: extract content, tools
                parts = parts_by_msg.get(mrow["id"], [])
                tools = []
                for part_str in parts:
                    try:
                        pdata = json.loads(part_str) if isinstance(part_str, str) else (part_str or {})
                    except json.JSONDecodeError:
                        continue
                    ptype = pdata.get("type", "")
                    if ptype == "tool":
                        tool_name = pdata.get("tool", "?")
                        tools.append(tool_name)

                msg.tools_used = tools

                # Stash text parts into _raw for chat view compatibility
                parsed_parts = []
                for p in parts:
                    if p is None:
                        continue
                    try:
                        parsed = json.loads(p) if isinstance(p, str) else p
                        if isinstance(parsed, dict):
                            parsed_parts.append(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass
                msg._raw["_parts"] = parsed_parts

                sess.messages.append(msg)

                # Capture first user message
                if role == "user" and sess.first_user_msg is None:
                    for part_str in parts:
                        try:
                            pdata = json.loads(part_str) if isinstance(part_str, str) else (part_str or {})
                        except json.JSONDecodeError:
                            continue
                        if pdata.get("type") == "text":
                            sess.first_user_msg = (pdata.get("text", "") or "")[:300]
                            break

            sess.line_count = len(sess.messages)
            sessions.append(sess)

    finally:
        conn.close()

    return sessions


# ═══════════════════════════════════════════════════════════════════════════════
# Opencode parser
# ═══════════════════════════════════════════════════════════════════════════════


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
            # Project name: prefer workspace directory, fallback to session directory
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

            # Pre-computed token totals (store on session for stats)
            pre_input = srow["tokens_input"] or 0
            pre_output = srow["tokens_output"] or 0
            pre_cache_read = srow["tokens_cache_read"] or 0
            pre_cache_write = srow["tokens_cache_write"] or 0

            # Load messages for this session
            msg_rows = conn.execute(
                "SELECT id, data, time_created FROM message WHERE session_id = ? ORDER BY time_created",
                (sid,),
            ).fetchall()

            # Build message ID lookup for parts
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

                # Model info: Opencode stores modelID/providerID at top level
                msg.model = mdata.get("modelID", "") or ""
                if not msg.model:
                    model_info = mdata.get("model", {})
                    if isinstance(model_info, dict):
                        msg.model = model_info.get("modelID", "") or ""

                # Extract message-level token data from JSON
                tok = mdata.get("tokens", {})
                if isinstance(tok, dict):
                    msg.input_tokens = tok.get("input", 0) or 0
                    msg.output_tokens = tok.get("output", 0) or 0
                    msg.cache_read_tokens = tok.get("cache_read", 0) or 0
                    msg.cache_create_tokens = tok.get("cache_write", 0) or 0
                    tokens_assigned += msg.input_tokens + msg.output_tokens

                # Parts: extract tools
                parts = parts_by_msg.get(mrow["id"], [])
                tools = []
                for part_str in parts:
                    try:
                        pdata = json.loads(part_str) if isinstance(part_str, str) else (part_str or {})
                    except json.JSONDecodeError:
                        continue
                    ptype = pdata.get("type", "")
                    if ptype == "tool":
                        tool_name = pdata.get("tool", "?")
                        tools.append(tool_name)

                msg.tools_used = tools

                # Stash text parts into _raw for chat view compatibility
                parsed_parts = []
                for p in parts:
                    if p is None:
                        continue
                    try:
                        parsed = json.loads(p) if isinstance(p, str) else p
                        if isinstance(parsed, dict):
                            parsed_parts.append(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass
                msg._raw["_parts"] = parsed_parts

                sess.messages.append(msg)

                # Capture first user message
                if role == "user" and sess.first_user_msg is None:
                    for part_str in parts:
                        try:
                            pdata = json.loads(part_str) if isinstance(part_str, str) else (part_str or {})
                        except json.JSONDecodeError:
                            continue
                        if pdata.get("type") == "text":
                            sess.first_user_msg = (pdata.get("text", "") or "")[:300]
                            break

            # Fallback: if message-level tokens are all 0, use session-level pre-computed totals
            if tokens_assigned == 0 and sess.messages:
                assistant_msgs = [m for m in sess.messages if m.msg_type == "assistant"]
                if assistant_msgs:
                    first = assistant_msgs[0]
                    first.input_tokens = pre_input
                    first.output_tokens = pre_output
                    first.cache_read_tokens = pre_cache_read
                    first.cache_create_tokens = pre_cache_write
                else:
                    # No assistant messages — create a synthetic one for stats
                    placeholder = assistant_msgs[-1] if assistant_msgs else sess.messages[-1]
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


# ═══════════════════════════════════════════════════════════════════════════════
# Antigravity parser
# ═══════════════════════════════════════════════════════════════════════════════


def parse_antigravity_sessions() -> list:
    """Parse Antigravity sessions from ~/.gemini/antigravity/brain/ transcript files.

    Each brain directory (UUID-named) contains a .system_generated/logs/transcript.jsonl
    with conversation steps. No per-message token counts or model identifiers are
    available in the transcript format, so token/cost fields will be 0.
    """
    from datetime import datetime

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
                created = d.get("created_at", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        sess.started_at = int(dt.timestamp())
                    except (ValueError, TypeError):
                        pass

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


def parse_sessions(source: str = "all") -> list:
    """Parse all sessions from all sources. Returns list of Session objects.

    Args:
        source: "claude", "freebuff", "mimo", "opencode", "antigravity", or "all"
        ("claude" merges projects + local-agent)

    For 'all', consider using parse_sessions_parallel() which is ~3-4x faster.
    """
    sessions = []

    sources_to_parse = []
    if source in ("projects", "local-agent", "claude", "all"):
        sources_to_parse.append(("projects", PROJECTS_DIR))
        sources_to_parse.append(("local-agent", LOCAL_AGENT_DIR))
    if source in ("freebuff", "all"):
        sessions.extend(parse_freebuff_sessions())
    if source in ("mimo", "all"):
        sessions.extend(parse_mimo_sessions())
    if source in ("opencode", "all"):
        sessions.extend(parse_opencode_sessions())
    if source in ("antigravity", "all"):
        sessions.extend(parse_antigravity_sessions())

    for src_label, src_dir in sources_to_parse:
        jsonl_files = _find_jsonl_files(src_dir)
        for filepath in jsonl_files:
            session_id = os.path.splitext(os.path.basename(filepath))[0]
            project = project_name_from_path(filepath, src_label)

            sess = Session(
                session_id=session_id,
                source=src_label,
                project=project,
                filepath=filepath,
            )

            with open(filepath, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    sess.line_count += 1

                    # Extract real timestamp from JSONL content (before parse_message)
                    if sess.started_at is None:
                        try:
                            raw = json.loads(line)
                            ts_str = raw.get("timestamp") or raw.get("_audit_timestamp")
                            if ts_str:
                                sess.started_at = _parse_iso_to_epoch(ts_str)
                        except (json.JSONDecodeError, KeyError):
                            pass

                    msg = parse_message(line)
                    if msg:
                        sess.messages.append(msg)
                        # Capture first user message (reuse already-loaded line dict)
                        if msg.msg_type == "user" and sess.first_user_msg is None:
                            try:
                                inner = msg._raw.get("message", {})
                                content = inner.get("content", "")
                                if isinstance(content, list):
                                    text = " ".join(
                                        b.get("text", "")
                                        for b in content
                                        if b.get("type") == "text"
                                    )
                                elif isinstance(content, str):
                                    text = content
                                else:
                                    text = str(content)[:200]
                                sess.first_user_msg = text[:300]
                            except Exception:
                                pass

            sessions.append(sess)

    return sessions


def parse_sessions_parallel(source: str = "all", max_workers: int = 4) -> list:
    """Parse sessions from multiple sources in parallel using threads.

    Thread-level parallelism works well here because each parser is
    I/O-bound (reading from files or SQLite databases).

    For 'all', this is ~3-4x faster than the sequential version.
    For individual sources, falls back to sequential parse.
    """
    if source == "all":
        # Map source labels to parse functions
        tasks = {
            "claude": lambda: parse_sessions("claude"),
            "freebuff": parse_freebuff_sessions,
            "mimo": parse_mimo_sessions,
            "opencode": parse_opencode_sessions,
            "antigravity": parse_antigravity_sessions,
        }
    else:
        return parse_sessions(source)

    all_sessions = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as executor:
        futures = {executor.submit(fn): label for label, fn in tasks.items()}
        for future in as_completed(futures):
            label = futures[future]
            try:
                result = future.result()
                all_sessions.extend(result)
            except Exception as e:
                # Log but don't fail — one source failing shouldn't block the rest
                print(f"[claude-analyzer] WARNING: failed to parse {label}: {e}", file=sys.stderr)

    return all_sessions


def parse_session_registry() -> dict:
    """Load session registry (sessions/*.json) keyed by sessionId."""
    registry = {}
    if not os.path.isdir(SESSIONS_DIR):
        return registry
    for f in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(f) as fh:
                d = json.load(fh)
            sid = d.get("sessionId")
            if sid:
                registry[sid] = {
                    "name": d.get("name"),
                    "kind": d.get("kind"),
                    "cwd": d.get("cwd"),
                    "started_at": d.get("startedAt"),
                }
        except (json.JSONDecodeError, IOError):
            pass
    return registry


def enrich_sessions(sessions: list) -> None:
    """Join session registry data into Session objects in-place.

    Sets started_at from the registry when available, otherwise falls back
    to the JSONL file's modification time (same approach as the Freebuff parser).
    """
    registry = parse_session_registry()
    for sess in sessions:
        info = registry.get(sess.session_id)
        if info:
            sess.name = info.get("name")
            sess.kind = info.get("kind")
            sess.cwd = info.get("cwd")
            sess.started_at = info.get("started_at")

        # Fallback: use file modification time
        if sess.started_at is None and os.path.isfile(sess.filepath):
            try:
                sess.started_at = int(os.path.getmtime(sess.filepath))
            except OSError:
                pass
