"""Parse Claude session data from .claude directories."""

import json
import os
import glob
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# --- Configurable paths ---
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
LOCAL_AGENT_DIR = os.path.expanduser(
    "~/Library/Application Support/Claude/local-agent-mode-sessions"
)
SESSIONS_DIR = os.path.expanduser("~/.claude/sessions")


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


def _find_jsonl_files(root: str) -> list:
    """Recursively find all .jsonl files under root."""
    if not os.path.isdir(root):
        return []
    return glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)


def _project_from_path(filepath: str, source: str) -> str:
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
                short = short.replace("-", " ")
                # Collapse empty
                short = " ".join(w for w in short.split() if w)
                # Truncate long names
                if len(short) > 50:
                    short = short[:47] + "..."
                return short
        return "unknown"
    else:
        return "local-agent"


def parse_sessions(source: str = "all") -> list:
    """Parse all sessions from both sources. Returns list of Session objects.

    Args:
        source: "projects", "local-agent", or "all"
    """
    sessions = []

    sources_to_parse = []
    if source in ("projects", "all"):
        sources_to_parse.append(("projects", PROJECTS_DIR))
    if source in ("local-agent", "all"):
        sources_to_parse.append(("local-agent", LOCAL_AGENT_DIR))

    for src_label, src_dir in sources_to_parse:
        jsonl_files = _find_jsonl_files(src_dir)
        for filepath in jsonl_files:
            session_id = os.path.splitext(os.path.basename(filepath))[0]
            project = _project_from_path(filepath, src_label)

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
    """Join session registry data into Session objects in-place."""
    registry = parse_session_registry()
    for sess in sessions:
        info = registry.get(sess.session_id)
        if info:
            sess.name = info.get("name")
            sess.kind = info.get("kind")
            sess.cwd = info.get("cwd")
            sess.started_at = info.get("started_at")
