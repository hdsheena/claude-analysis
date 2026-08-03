"""Live parser smoke tests.

Run the real parsers over real data and assert they produce non-degenerate
output. Catches both parser crashes and the silent-degradation pattern where
a parser swallows an error and returns an empty list.

Each test skips when its source is absent, keeping the suite portable.
"""

import unittest

from claude_analyzer.parser import (
    enrich_sessions,
    parse_session_registry,
    parse_sessions,
)
from claude_analyzer.parser_antigravity import parse_antigravity_sessions
from claude_analyzer.parser_freebuff import parse_freebuff_sessions
from claude_analyzer.parser_mimo import parse_mimo_sessions
from claude_analyzer.parser_opencode import parse_opencode_sessions


def _assistant_tokens(sessions) -> int:
    return sum(
        m.input_tokens + m.output_tokens
        for s in sessions
        for m in s.messages
        if m.msg_type == "assistant"
    )


class TestClaudeLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = parse_sessions("claude")
        cls.registry = parse_session_registry()

    def test_claude_sessions_parse_with_tokens(self):
        if not self.sessions:
            self.skipTest("no claude projects data")
        self.assertGreater(
            _assistant_tokens(self.sessions), 0,
            "assistant token data did not flow through the parser",
        )

    def test_registry_enrichment(self):
        if not self.sessions:
            self.skipTest("no claude projects data")
        self.assertGreater(len(self.registry), 0, "session registry is empty")
        enrich_sessions(self.sessions)
        started = [s for s in self.sessions if s.started_at is not None]
        self.assertGreater(
            len(started), 0,
            "no session got a started_at timestamp from registry or mtime",
        )


class TestOpencodeLive(unittest.TestCase):
    def test_sessions_parse(self):
        sessions = parse_opencode_sessions()
        if not sessions:
            self.skipTest("no opencode db")
        with_tokens = [
            s for s in sessions
            if any(m.input_tokens > 0 for m in s.messages)
        ]
        self.assertGreater(
            len(with_tokens), 0,
            "opencode token data did not flow through the parser",
        )


class TestMimoLive(unittest.TestCase):
    def test_sessions_parse(self):
        sessions = parse_mimo_sessions()
        if not sessions:
            self.skipTest("no mimo db")
        with_tokens = [
            s for s in sessions
            if any(m.input_tokens > 0 for m in s.messages)
        ]
        self.assertGreater(
            len(with_tokens), 0,
            "mimo token data did not flow through the parser",
        )


class TestFreebuffLive(unittest.TestCase):
    def test_sessions_parse(self):
        sessions = parse_freebuff_sessions()
        if not sessions:
            self.skipTest("no freebuff data")
        with_msgs = [s for s in sessions if s.messages]
        self.assertGreater(
            len(with_msgs), 0,
            "freebuff parser returned sessions with no messages",
        )


class TestAntigravityLive(unittest.TestCase):
    def test_sessions_parse(self):
        sessions = parse_antigravity_sessions()
        if not sessions:
            self.skipTest("no antigravity data")
        with_msgs = [s for s in sessions if s.messages]
        self.assertGreater(
            len(with_msgs), 0,
            "antigravity parser returned sessions with no messages",
        )


if __name__ == "__main__":
    unittest.main()
