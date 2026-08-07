"""Tests for the Copilot and Codex source parsers.

Builds small synthetic SQLite databases in a temp dir and points the
parser modules' path constants at them via mock.patch, so the tests
never touch the real ~/.copilot or ~/.codex data.
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from claude_analyzer.parser_copilot import parse_copilot_sessions, _to_epoch
from claude_analyzer.parser_codex import parse_codex_sessions


_COPILOT_SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, cwd TEXT, repository TEXT, host_type TEXT,
    branch TEXT, summary TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    turn_index INTEGER NOT NULL,
    user_message TEXT, assistant_response TEXT, timestamp TEXT,
    UNIQUE(session_id, turn_index)
);
CREATE TABLE assistant_usage_events (
    session_id TEXT, turn_index INTEGER, agent_id TEXT, model TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
    cache_write_tokens INTEGER, reasoning_tokens INTEGER,
    total_nano_aiu INTEGER, request_multiplier REAL, duration_ms INTEGER,
    time_to_first_token_ms INTEGER, inter_token_latency_ms INTEGER,
    initiator TEXT, api_endpoint TEXT, reasoning_effort TEXT,
    finish_reason TEXT, content_filter_triggered INTEGER,
    token_details_json TEXT, created_at TEXT
);
"""

_CODEX_COLUMNS = (
    "id, rollout_path, created_at, updated_at, source, model_provider, cwd, "
    "title, sandbox_policy, approval_mode, tokens_used, has_user_event, "
    "archived, archived_at, git_sha, git_branch, git_origin_url, cli_version, "
    "first_user_message, agent_nickname, agent_role, memory_mode, model, "
    "reasoning_effort, agent_path, created_at_ms, updated_at_ms, thread_source, "
    "preview, recency_at, recency_at_ms, history_mode, name, is_pinned"
)


def _build_copilot_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(_COPILOT_SCHEMA)
    conn.execute(
        """INSERT INTO sessions (id, cwd, repository, branch, summary, created_at)
           VALUES ('s1', '/Users/x/GitHub/evc', 'evc', 'main', 'review prs',
                   '2026-07-16T17:27:54.096Z')"""
    )
    conn.execute(
        """INSERT INTO turns (session_id, turn_index, user_message, assistant_response, timestamp)
           VALUES ('s1', 0, 'hello', 'hi there', '2026-07-16T17:27:54.096Z')"""
    )
    conn.execute(
        """INSERT INTO turns (session_id, turn_index, user_message, assistant_response, timestamp)
           VALUES ('s1', 1, 'thanks', 'welcome', '2026-07-16T17:28:00.000Z')"""
    )
    conn.execute(
        """INSERT INTO assistant_usage_events
           (session_id, turn_index, model, input_tokens, output_tokens,
            cache_read_tokens, cache_write_tokens, reasoning_tokens,
            total_nano_aiu, request_multiplier, created_at)
           VALUES ('s1', 0, 'gpt-5-mini', 100, 20, 10, 5, 8,
                   500000000, 1.0, '2026-07-16T17:27:54.096Z')"""
    )
    conn.commit()
    conn.close()


def _build_codex_db(path, rollout_path):
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE threads ({_CODEX_COLUMNS})")
    conn.execute(
        """INSERT INTO threads
           (id, rollout_path, created_at, updated_at, source, model_provider,
            cwd, title, sandbox_policy, approval_mode, tokens_used,
            first_user_message, model, preview)
           VALUES ('t1', ?, 1786000000, 1786000000, 'codex', 'openai',
                   '/Users/x/GitHub/evc', 'Fix the bug', 'workspace-write',
                   'never', 123456, 'can you fix', 'gpt-5.3-codex', 'fix the bug')""",
        (rollout_path,),
    )
    conn.commit()
    conn.close()


class TestCopilotParser(unittest.TestCase):
    def test_parses_sessions_turns_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "session-store.db")
            _build_copilot_db(db)
            with mock.patch("claude_analyzer.parser_copilot.COPILOT_DB_PATH", db):
                sessions = parse_copilot_sessions()

        self.assertEqual(len(sessions), 1)
        sess = sessions[0]
        self.assertEqual(sess.source, "copilot")
        self.assertEqual(sess.project, "evc")
        self.assertEqual(sess.first_user_msg, "hello")
        self.assertEqual(len(sess.messages), 4)  # user, assistant, user, assistant

        asst_with_tokens = [m for m in sess.messages
                            if m.msg_type == "assistant" and m.input_tokens]
        self.assertEqual(len(asst_with_tokens), 1)
        self.assertEqual(asst_with_tokens[0].model, "gpt-5-mini")
        self.assertEqual(asst_with_tokens[0].input_tokens, 100)
        self.assertEqual(asst_with_tokens[0].output_tokens, 20)
        self.assertEqual(asst_with_tokens[0].cache_read_tokens, 10)

        usage = getattr(sess, "_usage_events", [])
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0]["total_nano_aiu"], 500000000)

        expected_epoch = int(
            datetime.fromisoformat("2026-07-16T17:27:54.096Z"
                                   .replace("Z", "+00:00")).timestamp()
        )
        self.assertEqual(sess.started_at, expected_epoch)

    def test_missing_db_returns_empty(self):
        with mock.patch("claude_analyzer.parser_copilot.COPILOT_DB_PATH",
                        "/nonexistent/session-store.db"):
            self.assertEqual(parse_copilot_sessions(), [])


class TestCopilotEpoch(unittest.TestCase):
    def test_iso_format(self):
        self.assertEqual(_to_epoch("2026-07-16T17:27:54.096Z"),
                         int(datetime.fromisoformat("2026-07-16T17:27:54.096Z"
                                                    .replace("Z", "+00:00")).timestamp()))

    def test_space_datetime_format(self):
        expected = int(datetime.strptime("2026-07-16 17:27:54", "%Y-%m-%d %H:%M:%S").timestamp())
        self.assertEqual(_to_epoch("2026-07-16 17:27:54"), expected)

    def test_garbage_returns_zero(self):
        self.assertEqual(_to_epoch("not-a-date"), 0)
        self.assertEqual(_to_epoch(None), 0)


class TestCodexParser(unittest.TestCase):
    def test_parses_threads_with_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = os.path.join(tmp, "rollout.jsonl")
            with open(rollout, "w") as fh:
                fh.write("{\"type\": \"session_meta\"}\n")
            db = os.path.join(tmp, "state_5.sqlite")
            _build_codex_db(db, rollout)
            expected_size = os.path.getsize(rollout)
            with mock.patch("claude_analyzer.parser_codex.CODEX_DB_PATH", db):
                sessions = parse_codex_sessions()

        self.assertEqual(len(sessions), 1)
        sess = sessions[0]
        self.assertEqual(sess.source, "codex")
        self.assertEqual(sess.project, "evc")
        self.assertEqual(sess.name, "Fix the bug")
        self.assertEqual(sess.first_user_msg, "can you fix")
        self.assertEqual(sess.started_at, 1786000000)
        self.assertEqual(sess.size_bytes, expected_size)

        self.assertEqual(len(sess.messages), 1)
        msg = sess.messages[0]
        self.assertEqual(msg.model, "gpt-5.3-codex")
        self.assertEqual(msg.input_tokens, 123456)

    def test_missing_rollout_degrades_to_zero_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "state_5.sqlite")
            missing_rollout = os.path.join(tmp, "nope.jsonl")
            _build_codex_db(db, missing_rollout)
            with mock.patch("claude_analyzer.parser_codex.CODEX_DB_PATH", db):
                sessions = parse_codex_sessions()
        self.assertEqual(sessions[0].size_bytes, 0)

    def test_missing_db_returns_empty(self):
        with mock.patch("claude_analyzer.parser_codex.CODEX_DB_PATH",
                        "/nonexistent/state_5.sqlite"):
            self.assertEqual(parse_codex_sessions(), [])


class TestSourceWiring(unittest.TestCase):
    def test_parse_sessions_routes_new_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "session-store.db")
            _build_copilot_db(db)
            with mock.patch("claude_analyzer.parser_copilot.COPILOT_DB_PATH", db):
                from claude_analyzer.parser import parse_sessions
                sessions = parse_sessions(source="copilot")
        self.assertTrue(all(s.source == "copilot" for s in sessions))
        self.assertGreaterEqual(len(sessions), 1)


if __name__ == "__main__":
    unittest.main()
