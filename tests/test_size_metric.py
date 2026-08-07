"""Regression tests for the per-session disk-size metric.

Guards against the bug where SQLite-backed sessions (opencode/mimo) shared a
single filepath pointing at the whole database, so os.path.getsize() added the
full DB file size once per session — reporting terabytes of phantom disk usage.
"""

import unittest

from claude_analyzer.parser import Session
from claude_analyzer.stats import compute_stats


def _session(source="projects", size_bytes=0):
    return Session(
        session_id="s1",
        source=source,
        project="proj",
        filepath="/nonexistent/shared.db",
        size_bytes=size_bytes,
    )


class TestSizeMetric(unittest.TestCase):
    def test_uses_per_session_size(self):
        sess = _session(size_bytes=1024)
        stats = compute_stats([sess])
        self.assertAlmostEqual(stats.total_size_mb, 1024 / (1024 * 1024))
        self.assertEqual(stats.project_size["proj"], 1024)

    def test_shared_db_counted_once_not_per_session(self):
        one = compute_stats([_session("opencode", 0)])
        two = compute_stats([_session("opencode", 0), _session("opencode", 0)])
        self.assertAlmostEqual(one.total_size_mb, two.total_size_mb)

    def test_shared_db_sessions_report_zero_project_size(self):
        stats = compute_stats([_session("opencode", 0)])
        self.assertEqual(stats.project_size["proj"], 0)

    def test_missing_size_bytes_degrades_to_zero(self):
        sess = Session(
            session_id="s1",
            source="opencode",
            project="proj",
            filepath="/nonexistent/shared.db",
        )
        stats = compute_stats([sess])
        self.assertEqual(stats.project_size["proj"], 0)


if __name__ == "__main__":
    unittest.main()
