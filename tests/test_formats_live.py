"""Live on-disk format guards.

Read the real data sources on this machine and assert the shapes the parsers
depend on still hold, so a tool update that renames a field fails loudly
instead of silently degrading the dashboard to zeros/empty.

Each test skips when its source is absent, keeping the suite portable.
"""

import glob
import json
import os
import sqlite3
import unittest

from claude_analyzer.parser import (
    ANTIGRAVITY_BRAIN_DIR,
    FREE_BUFF_PROJECTS_DIR,
    MIMO_DB_PATH,
    OPENCODE_DB_PATH,
)

PROJECTS_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
REGISTRY_GLOB = os.path.expanduser("~/.claude/sessions/*.json")
CHAT_GLOB = os.path.join(FREE_BUFF_PROJECTS_DIR, "*", "chats", "*", "chat-messages.json")
TRANSCRIPT_GLOB = os.path.join(ANTIGRAVITY_BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl")

OPCODE_SCHEMA = {
    "session": [
        "id", "slug", "title", "directory", "workspace_id", "agent", "model",
        "tokens_input", "tokens_output", "tokens_cache_read",
        "tokens_cache_write", "time_created", "time_updated",
    ],
    "workspace": ["id", "directory"],
    "message": ["id", "session_id", "data", "time_created"],
    "part": ["message_id", "data"],
}

MIMO_SCHEMA = {
    "session": [
        "id", "project_id", "slug", "title", "directory", "time_created",
        "summary_additions", "summary_deletions", "summary_files", "summary_diffs",
    ],
    "project": ["id", "worktree", "vcs"],
    "message": ["id", "session_id", "data", "time_created"],
    "part": ["message_id", "data"],
}


def _table_columns(db_path: str, table: str) -> set:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


class TestClaudeJsonlFormat(unittest.TestCase):
    USAGE_KEYS = {
        "input_tokens", "output_tokens",
        "cache_read_input_tokens", "cache_creation_input_tokens",
    }

    def _first_assistant_usage(self):
        for f in sorted(glob.glob(PROJECTS_GLOB))[:8]:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    usage = (d.get("message") or {}).get("usage")
                    if isinstance(usage, dict):
                        return f, usage
        return None, None

    def test_assistant_usage_has_token_keys(self):
        if not glob.glob(PROJECTS_GLOB):
            self.skipTest("no claude projects data")
        f, usage = self._first_assistant_usage()
        self.assertIsNotNone(usage, "no assistant message with usage found")
        missing = sorted(self.USAGE_KEYS - set(usage.keys()))
        self.assertEqual(missing, [], f"assistant usage in {f} missing {missing}")


class TestClaudeRegistryFormat(unittest.TestCase):
    REQUIRED = ("sessionId", "name", "kind", "cwd", "startedAt")

    def test_registry_files_have_required_keys(self):
        files = sorted(glob.glob(REGISTRY_GLOB))
        if not files:
            self.skipTest("no session registry data")
        for f in files[:20]:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            for key in self.REQUIRED:
                self.assertIn(key, d, f"{f} missing {key}")


class TestOpencodeSchema(unittest.TestCase):
    def test_required_columns(self):
        if not os.path.isfile(OPENCODE_DB_PATH):
            self.skipTest("no opencode db")
        for table, cols in OPCODE_SCHEMA.items():
            missing = sorted(set(cols) - _table_columns(OPENCODE_DB_PATH, table))
            self.assertEqual(missing, [], f"opencode.{table} missing {missing}")


class TestMimoSchema(unittest.TestCase):
    def test_required_columns(self):
        if not os.path.isfile(MIMO_DB_PATH):
            self.skipTest("no mimo db")
        for table, cols in MIMO_SCHEMA.items():
            missing = sorted(set(cols) - _table_columns(MIMO_DB_PATH, table))
            self.assertEqual(missing, [], f"mimo.{table} missing {missing}")


class TestFreebuffFormat(unittest.TestCase):
    def test_chat_messages_shape(self):
        files = sorted(glob.glob(CHAT_GLOB))
        if not files:
            self.skipTest("no freebuff data")
        with open(files[0], encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertIsInstance(d, list)
        for m in d:
            self.assertIsInstance(m, dict)
            self.assertIn("variant", m)
            if "blocks" in m:
                self.assertIsInstance(m["blocks"], list)
                for b in m["blocks"]:
                    self.assertIsInstance(b, dict)

    def test_meta_has_first_prompt(self):
        files = sorted(glob.glob(CHAT_GLOB))
        if not files:
            self.skipTest("no freebuff data")
        meta = os.path.join(os.path.dirname(files[0]), "chat-meta.json")
        self.assertTrue(os.path.isfile(meta), "chat-meta.json missing")
        with open(meta, encoding="utf-8") as fh:
            self.assertIn("firstPrompt", json.load(fh))


class TestAntigravityFormat(unittest.TestCase):
    def test_transcript_lines_parse_and_have_source(self):
        files = sorted(glob.glob(TRANSCRIPT_GLOB))
        if not files:
            self.skipTest("no antigravity data")
        seen = False
        with open(files[0], encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                d = json.loads(line)
                self.assertIn("source", d)
                self.assertIn("created_at", d)
                if d.get("source") in ("MODEL", "USER_EXPLICIT"):
                    seen = True
        self.assertTrue(seen, "no MODEL/USER_EXPLICIT entries found")


if __name__ == "__main__":
    unittest.main()
