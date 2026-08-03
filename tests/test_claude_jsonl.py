"""Unit tests for Claude JSONL line parsing and shared name helpers.

Fixture-based: these guard the parser against regression, so a field rename
or logic change in parse_message fails loudly instead of silently producing
zero tokens and empty tool lists.
"""

import json
import os
import unittest

from claude_analyzer.parser import (
    _parse_parts,
    normalize_project_name,
    parse_message,
    project_name_from_path,
)


ASSISTANT_LINE = json.dumps({
    "type": "assistant",
    "timestamp": "2026-06-15T17:37:56.893Z",
    "message": {
        "model": "claude-sonnet-4-20250514",
        "content": [
            {"type": "text", "text": "working"},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
        ],
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 1234,
            "output_tokens": 200,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 900,
        },
    },
})


class TestParseMessage(unittest.TestCase):
    def test_assistant_tokens_extracted(self):
        msg = parse_message(ASSISTANT_LINE)
        self.assertEqual(msg.msg_type, "assistant")
        self.assertEqual(msg.model, "claude-sonnet-4-20250514")
        self.assertEqual(msg.input_tokens, 1234)
        self.assertEqual(msg.output_tokens, 200)
        self.assertEqual(msg.cache_read_tokens, 800)
        self.assertEqual(msg.cache_create_tokens, 900)

    def test_tool_use_names_extracted(self):
        msg = parse_message(ASSISTANT_LINE)
        self.assertEqual(msg.tools_used, ["Bash"])

    def test_malformed_line_returns_none(self):
        self.assertIsNone(parse_message("{not json"))

    def test_missing_usage_defaults_to_zero(self):
        line = json.dumps({"type": "assistant", "message": {"content": []}})
        msg = parse_message(line)
        self.assertEqual(msg.input_tokens, 0)
        self.assertEqual(msg.cache_read_tokens, 0)
        self.assertEqual(msg.cache_create_tokens, 0)

    def test_user_message(self):
        line = json.dumps({"type": "user", "message": {"content": "hi"}})
        msg = parse_message(line)
        self.assertEqual(msg.msg_type, "user")

    def test_non_object_content_blocks_skipped(self):
        line = json.dumps({"type": "assistant", "message": {"content": ["string-block"]}})
        msg = parse_message(line)
        self.assertEqual(msg.tools_used, [])


class TestParseParts(unittest.TestCase):
    def test_tool_part_extracts_tool_name(self):
        tools, parts = _parse_parts([json.dumps({"type": "tool", "tool": "bash"})])
        self.assertEqual(tools, ["bash"])
        self.assertEqual(parts[0]["type"], "tool")

    def test_none_and_garbage_parts_skipped(self):
        tools, parts = _parse_parts([None, "not json", {"type": "text", "text": "hi"}])
        self.assertEqual(tools, [])
        self.assertEqual(len(parts), 1)


class TestNormalizeProjectName(unittest.TestCase):
    def test_hyphens_and_underscores(self):
        self.assertEqual(normalize_project_name("my-project_2"), "my project 2")

    def test_collapse_whitespace(self):
        self.assertEqual(normalize_project_name("  foo--bar  "), "foo bar")

    def test_dedupe_consecutive_words(self):
        self.assertEqual(normalize_project_name("repo repo"), "repo")

    def test_strips_timestamp_suffix(self):
        self.assertEqual(normalize_project_name("proj 20260624T1645"), "proj")

    def test_strips_run_number(self):
        self.assertEqual(normalize_project_name("proj run 11"), "proj")

    def test_empty_is_unknown(self):
        self.assertEqual(normalize_project_name(""), "unknown")


class TestProjectNameFromPath(unittest.TestCase):
    def test_projects_path(self):
        p = os.path.expanduser(
            "~/.claude/projects/-Users-m4mbp-GitHub-my-repo/abc.jsonl"
        )
        self.assertEqual(project_name_from_path(p, "projects"), "my repo")

    def test_local_agent_source(self):
        self.assertEqual(project_name_from_path("/x/y/z", "local-agent"), "local-agent")

    def test_unknown_project(self):
        self.assertEqual(project_name_from_path("/plain/path.jsonl", "projects"), "unknown")


if __name__ == "__main__":
    unittest.main()
