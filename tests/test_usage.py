"""Tests for claude_analyzer/usage.py burn-rate, pacing, and cap projections."""

from datetime import datetime, timedelta

from claude_analyzer.parser import Message, Session
from claude_analyzer.usage import (
    METRIC_REQUESTS, METRIC_TOKENS,
    compute_source_burns, load_caps, project_caps, save_caps,
    usage_report, usage_report_json,
)

NOW = datetime(2026, 8, 6, 12, 0, 0).timestamp()


def _sess(source: str, day_offset: int, tokens: int = 0,
          n_assist: int = 0, hour: int = 12) -> Session:
    dt = datetime(2026, 8, 6, hour, 0, 0) - timedelta(days=day_offset)
    sess = Session(
        session_id=f"t-{source}-{day_offset}-{hour}",
        source=source, project="proj", filepath="", size_bytes=0,
    )
    sess.started_at = int(dt.timestamp())
    if tokens:
        sess.messages.append(Message(
            msg_type="assistant", model="test", input_tokens=tokens))
    for _ in range(n_assist):
        sess.messages.append(Message(msg_type="assistant"))
    return sess


def test_tokens_burn_windows_and_projection():
    sessions = [
        _sess("claude", 0, tokens=1000),
        _sess("claude", 5, tokens=2000),
        _sess("claude", 40, tokens=4000),
    ]
    b = compute_source_burns(sessions, NOW)["claude"]

    assert b["metric"] == METRIC_TOKENS
    assert b["today"] == 1000
    assert b["mtd"] == 3000                      # day 0 + day 5, both Aug 2026
    assert b["mtd_days"] == 6
    assert b["last7"] == 3000
    assert b["last30"] == 3000                   # day 40 is June, out of window
    assert b["last90"] == 7000
    assert round(b["avg30"], 1) == 100.0         # 3000 / 30
    # mtd + avg30 * (31 - 6) = 3000 + 100 * 25
    assert b["proj_month_end"] == 5500
    assert b["last_month"] == 0
    assert b["pace_change_pct"] is None          # no prior month to compare


def test_request_sources_count_ai_calls():
    sessions = [
        _sess("copilot", 2, n_assist=3),
        _sess("copilot", 4, n_assist=5),
    ]
    b = compute_source_burns(sessions, NOW)["copilot"]

    assert b["metric"] == METRIC_REQUESTS
    assert b["mtd"] == 8
    assert b["last7"] == 8
    assert round(b["avg30"], 1) == round(8 / 30, 1)


def test_hourly_bucketing():
    sessions = [
        _sess("mimo", 0, tokens=100, hour=9),
        _sess("mimo", 1, tokens=300, hour=17),
    ]
    b = compute_source_burns(sessions, NOW)["mimo"]
    assert b["hourly"] == {9: 100, 17: 300}


def test_week_cap_projection():
    sessions = [
        _sess("codex", 0, tokens=50_000_000),
        _sess("codex", 1, tokens=50_000_000),
    ]
    burns = compute_source_burns(sessions, NOW)
    caps = {"codex": {"metric": METRIC_TOKENS, "cap": 250_000_000, "period": "week"}}
    p = project_caps(burns, caps, NOW)[0]

    assert p["used"] == 100_000_000              # Mon Aug 3 - Thu Aug 6
    assert p["cap"] == 250_000_000
    assert p["remaining"] == 150_000_000
    assert p["projected"] == 110_000_000         # used + avg30 * 3 remaining days
    assert p["projected_over_cap"] is False
    assert p["days_left"] == round(150_000_000 / (100_000_000 / 30), 1)


def test_exhausted_cap_gets_date():
    sessions = [_sess("codex", 0, tokens=200_000_000)]
    burns = compute_source_burns(sessions, NOW)
    caps = {"codex": {"metric": METRIC_TOKENS, "cap": 100_000_000, "period": "week"}}
    p = project_caps(burns, caps, NOW)[0]
    assert p["used"] == 200_000_000
    assert p["remaining"] == 0
    assert p["projected_over_cap"] is True
    assert p["est_exhaust_date"] == "2026-08-06"


def test_month_cap_projection():
    sessions = [
        _sess("copilot", 2, n_assist=3),
        _sess("copilot", 4, n_assist=5),
    ]
    burns = compute_source_burns(sessions, NOW)
    caps = {"copilot": {"metric": METRIC_REQUESTS, "cap": 100, "period": "month"}}
    p = project_caps(burns, caps, NOW)[0]
    assert p["used"] == 8
    assert p["remaining"] == 92
    assert p["projected"] == 14                 # 8 + (8/30) * 25


def test_unknown_source_cap_ignored():
    sessions = [_sess("mimo", 0, tokens=100)]
    burns = compute_source_burns(sessions, NOW)
    caps = {"not_a_source": {"metric": METRIC_TOKENS, "cap": 1, "period": "week"}}
    assert project_caps(burns, caps, NOW) == []


def test_month_cap_reset_day_spans_previous_month():
    # reset_day=26, today Aug 6 → cycle Jul 26..Aug 26 (exclusive end).
    sessions = [
        _sess("codex", 3, tokens=10_000_000),      # Aug 3  → in cycle
        _sess("codex", 35, tokens=99_000_000),     # Jul 2  → before cycle
        _sess("codex", 40, tokens=99_000_000),     # Jun 27 → before cycle
    ]
    burns = compute_source_burns(sessions, NOW)
    caps = {"codex": {"metric": METRIC_TOKENS, "cap": 100_000_000,
                      "period": "month", "reset_day": 26}}
    p = project_caps(burns, caps, NOW)[0]

    assert p["reset_day"] == 26
    assert p["cycle_start"] == "2026-07-26"
    assert p["cycle_end"] == "2026-08-26"
    assert p["used"] == 10_000_000                 # only Aug 3 counts
    assert p["remaining"] == 90_000_000
    assert p["days_left"] is not None


def test_month_cap_reset_day_before_today():
    # reset_day=2, today Aug 6 → cycle Aug 2..Sep 2.
    sessions = [
        _sess("codex", 1, tokens=5_000_000),       # Aug 5  → in cycle
        _sess("codex", 6, tokens=9_000_000),       # Jul 31 → before cycle
        _sess("codex", 31, tokens=9_000_000),      # Jul 6  → before cycle
    ]
    burns = compute_source_burns(sessions, NOW)
    caps = {"codex": {"metric": METRIC_TOKENS, "cap": 50_000_000,
                      "period": "month", "reset_day": 2}}
    p = project_caps(burns, caps, NOW)[0]

    assert p["cycle_start"] == "2026-08-02"
    assert p["cycle_end"] == "2026-09-02"
    assert p["used"] == 5_000_000
    # remaining days = Sep 2 - Aug 6 - 1 = 26; avg30 covers all last-30d burn
    assert p["projected"] == int(5_000_000 + burns["codex"]["avg30"] * 26)


def test_reset_day_clamped_to_month_length():
    # reset_day=31, today Aug 6 → prev month Jul 31, end Aug 31.
    sessions = [_sess("codex", 3, tokens=1_000_000)]  # Aug 3, in cycle
    burns = compute_source_burns(sessions, NOW)
    caps = {"codex": {"metric": METRIC_TOKENS, "cap": 10_000_000,
                      "period": "month", "reset_day": 31}}
    p = project_caps(burns, caps, NOW)[0]

    assert p["cycle_start"] == "2026-07-31"
    assert p["cycle_end"] == "2026-08-31"
    assert p["used"] == 1_000_000


def test_invalid_reset_day_falls_back_to_calendar_month():
    sessions = [_sess("codex", 3, tokens=1_000_000)]
    burns = compute_source_burns(sessions, NOW)
    for bad in (0, 32, "x", None):
        caps = {"codex": {"metric": METRIC_TOKENS, "cap": 10_000_000,
                          "period": "month", "reset_day": bad}}
        p = project_caps(burns, caps, NOW)[0]
        assert p["reset_day"] is None
        assert p["cycle_start"] == "2026-08-01"
        assert p["cycle_end"] == "2026-09-01"


def test_week_period_ignores_reset_day():
    sessions = [_sess("codex", 3, tokens=1_000_000)]
    burns = compute_source_burns(sessions, NOW)
    caps = {"codex": {"metric": METRIC_TOKENS, "cap": 10_000_000,
                      "period": "week", "reset_day": 26}}
    p = project_caps(burns, caps, NOW)[0]
    assert p["period"] == "week"
    assert p["reset_day"] is None
    assert p["cycle_start"] == "2026-08-03"        # Monday
    assert p["cycle_end"] == "2026-08-10"


def test_caps_roundtrip(tmp_path):
    path = str(tmp_path / "caps.json")
    caps = {"codex": {"metric": "tokens", "cap": 200000000, "period": "week"}}
    assert save_caps(caps, path) == path
    assert load_caps(path) == caps
    assert load_caps(str(tmp_path / "missing.json")) == {}


def test_undated_sessions_skipped():
    sess = _sess("claude", 0, tokens=1000)
    sess.started_at = None
    assert compute_source_burns([sess], NOW) == {}


def test_report_and_json_shape():
    sessions = [
        _sess("claude", 0, tokens=1000),
        _sess("copilot", 1, n_assist=4),
    ]
    caps = {"copilot": {"metric": METRIC_REQUESTS, "cap": 100, "period": "month"}}

    txt = usage_report(sessions, caps, NOW)
    assert "USAGE & PACING" in txt
    assert "claude" in txt and "copilot" in txt
    assert "days left" in txt

    data = usage_report_json(sessions, caps, NOW)
    assert set(data) == {"computed_at", "sources", "caps", "projections",
                         "hourly_total"}
    assert data["sources"]["claude"]["mtd"] == 1000
    assert data["projections"][0]["source"] == "copilot"
