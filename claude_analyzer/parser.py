"""Parse session data from all supported sources.

Types and helpers live here. Source-specific parsers are in separate modules:
    parser_freebuff, parser_mimo, parser_opencode, parser_antigravity
"""

import re
import json
import os
import sys
import glob
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# --- Configurable paths ---
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
LOCAL_AGENT_DIR = os.path.expanduser(
    "~/Library/Application Support/Claude/local-agent-mode-sessions"
)
SESSIONS_DIR = os.path.expanduser("~/.claude/sessions")

# Re-export source-parser paths for external reference
FREE_BUFF_PROJECTS_DIR = os.path.expanduser("~/.config/manicode/projects")
MIMO_DB_PATH = os.path.expanduser("~/.local/share/mimocode/mimocode.db")
OPENCODE_DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
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
    """One session."""
    session_id: str
    source: str  # "projects", "local-agent", "freebuff", "mimo", "opencode", "antigravity"
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


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

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


def _parse_parts(parts: list) -> tuple:
    """Parse Mimo/Opencode parts into (tools_list, parsed_parts)."""
    tools = []
    parsed_parts = []
    for p in parts:
        if p is None:
            continue
        try:
            pdata = json.loads(p) if isinstance(p, str) else (p or {})
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(pdata, dict):
            parsed_parts.append(pdata)
            if pdata.get("type") == "tool":
                tools.append(pdata.get("tool", "?"))
    return tools, parsed_parts


def _parse_iso_to_epoch(ts_str: str) -> Optional[int]:
    """Parse an ISO 8601 timestamp string to epoch seconds."""
    if not ts_str:
        return None
    try:
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

    # Remove duplicate consecutive words
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
    if source == "projects":
        for p in parts:
            if p.startswith("-Users-"):
                short = p.replace("-Users-m4mbp-", "").replace("-Users-m4mbp", "")
                short = short.replace("GitHub-", "").replace("Documents-GitHub-", "")
                short = normalize_project_name(short)
                if len(short) > 50:
                    short = short[:47] + "..."
                return short
        return "unknown"
    else:
        return "local-agent"


# ═══════════════════════════════════════════════════════════════════════════════
# Claude (JSONL) parser
# ═══════════════════════════════════════════════════════════════════════════════

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

                    msg = parse_message(line)
                    if msg:
                        # Extract real timestamp from JSONL content
                        if sess.started_at is None:
                            raw = msg._raw
                            ts_str = raw.get("timestamp") or raw.get("_audit_timestamp")
                            if ts_str:
                                sess.started_at = _parse_iso_to_epoch(ts_str)
                        sess.messages.append(msg)
                        # Capture first user message
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
                            except (AttributeError, TypeError, ValueError):
                                pass

            sessions.append(sess)

    return sessions


def parse_sessions_parallel(source: str = "all", max_workers: int = 5) -> list:
    """Parse sessions from multiple sources in parallel using threads.

    Thread-level parallelism works well here because each parser is
    I/O-bound (reading from files or SQLite databases).

    For 'all', this is ~3-4x faster than the sequential version.
    For individual sources, falls back to sequential parse.
    """
    if source == "all":
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
    to the JSONL file's modification time.
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


# --- Source parsers (imported at bottom to avoid circular imports) ---
from .parser_freebuff import parse_freebuff_sessions  # noqa: E402
from .parser_mimo import parse_mimo_sessions  # noqa: E402
from .parser_opencode import parse_opencode_sessions  # noqa: E402
from .parser_antigravity import parse_antigravity_sessions  # noqa: E402
