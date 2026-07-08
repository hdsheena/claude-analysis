# Claude Analytics

Analyze your Claude Code session history — plus Freebuff, Mimo, Opencode, and Antigravity sessions — for insights, usage patterns, cost tracking, memory file analysis, and cross-tool comparisons.

Parses JSONL session data, SQLite databases, and transcript files to give you a comprehensive picture of your AI coding activity across multiple tools.

## Quick Start

```bash
# CLI analysis
python3 analyze.py

# Streamlit dashboard (rich interactive UI)
streamlit run app.py
```

The CLI works with Python 3.9+ standard library only. The Streamlit dashboard requires `streamlit`, `pandas`, and `plotly`.

## Streamlit Dashboard

The dashboard runs on `localhost:8501` (or use `--server.port` to change it) and provides 7 pages:

| Page | What it shows |
|------|---------------|
| **Summary** | Top-level metrics, model usage, tool usage, cost by model, projects, session length distribution, stop reasons |
| **Timeline** | Time-series charts for tokens, sessions, cost, model trends, and cache hit rate over time |
| **Projects** | Per-project breakdown with bar charts, scatter plots, and detailed tables |
| **Sessions & Raw Data** | Session table with sort/filter, drill-down into individual sessions, chat view, and raw JSONL |
| **Compare** | Side-by-side comparison of two sessions or two projects with metrics and model charts |
| **Memory & Skills** | Memory file analysis, installed skills, plugins/marketplaces, repo-level config dirs, and data source inventory |
| **Antigravity** | Antigravity session viewer with thinking/reasoning blocks |

### Filters (sidebar)
- **Source**: all, claude, freebuff, mimo, opencode, antigravity
- **Project**: substring filter
- **Time range**: last week / month / 3mo / 6mo / year / all time
- **Refresh**: clears caches and reparses all data

## CLI Commands

```bash
python3 analyze.py                       # Full summary report (default)
python3 analyze.py --projects            # Per-project breakdown
python3 analyze.py --models              # Model usage details
python3 analyze.py --tools               # Tool usage breakdown
python3 analyze.py --sessions            # List top 20 sessions
python3 analyze.py --sessions 50         # List top 50 sessions
python3 analyze.py --project evc         # Filter by project name
python3 analyze.py --source local-agent  # Only local agent sessions
python3 analyze.py --all                 # Show everything
python3 analyze.py --json                # Output as JSON
python3 analyze.py --timeline weekly     # Time-series with sparklines
python3 analyze.py --diff a b            # Compare two sessions/projects
python3 analyze.py --memory              # Memory file analysis
python3 analyze.py --skills              # Installed skills analysis
python3 analyze.py --plugins             # Plugins analysis
python3 analyze.py --search-tool "trello"  # Search tool calls
```

## Data Sources

| Source | Path | Format |
|--------|------|--------|
| Claude Code (CLI) | `~/.claude/projects/` | JSONL files |
| Claude Desktop agent | `~/Library/Application Support/Claude/local-agent-mode-sessions/` | JSONL files |
| Claude session registry | `~/.claude/sessions/` | JSON metadata |
| Freebuff / Codebuff | `~/.config/manicode/projects/` | JSON files |
| Mimo | `~/.local/share/mimocode/mimocode.db` | SQLite |
| Opencode | `~/.local/share/opencode/opencode.db` | SQLite |
| Antigravity | `~/.gemini/antigravity/brain/` | transcript.jsonl files |

## Caching

Session data is cached per-source in a SQLite database at `.cache/sessions.db` (gzip-compressed pickle blobs). The cache:
- Has a 24-hour TTL
- Checks source file modification times for freshness
- Is prewarmed in a background thread after a cache clear
- Stores 7 entries: 5 session sources + repo tool directories + memory file data

## Architecture

```
claude-analysis/
├── app.py                          # Streamlit main page (Summary)
├── analyze.py                      # CLI entry point
├── shared.py                       # Shared data loaders, sidebar, filters
├── _memory_skills/                 # Memory_Skills tab submodules
│   ├── memory_tab.py
│   ├── skills_tab.py
│   ├── plugins_tab.py
│   ├── data_sources_tab.py
│   └── repo_configs_tab.py
├── claude_analyzer/
│   ├── __init__.py
│   ├── parser.py                   # Core data types + shared helpers
│   ├── parser_freebuff.py          # Freebuff session parser
│   ├── parser_mimo.py              # Mimo session parser
│   ├── parser_opencode.py          # Opencode session parser
│   ├── parser_antigravity.py       # Antigravity session parser
│   ├── stats.py                    # Aggregate statistics
│   ├── diff.py                     # Session/project comparison
│   ├── search.py                   # Tool call search
│   ├── timeline.py                 # Time-series analysis
│   ├── viz.py                      # CLI text visualization
│   ├── memory.py                   # Memory file analysis
│   ├── skills.py                   # Skills, plugins, repo config scan
│   └── disk_cache.py               # SQLite-backed disk cache
├── pages/                          # Streamlit multipage pages
│   ├── 1_Timeline.py
│   ├── 2_Projects.py
│   ├── 3_Sessions.py
│   ├── 4_Compare.py
│   ├── 5_Memory_Skills.py
│   └── 6_Antigravity.py
└── .cache/
    └── sessions.db                 # Disk cache (auto-created)
```

## Refactoring History

The codebase underwent a significant refactoring that:

- **Split the monolithic parser** (`parser.py`) into per-source modules — 500+ lines became 4 focused parsers + shared base
- **Eliminated duplicated logic** — shared `aggregate_message_stats()` removed the same message loop from `stats.py` and `diff.py`; shared `collect_memory_file_data()` and `scan_repo_tool_dirs()` unified memory/repo scanning between CLI and UI
- **Decomposed long Streamlit pages** — Sessions page cut from 483→362 lines, Memory_Skills page from 477→35 lines (extracted into 5 `_memory_skills/` submodules)
- **Added return type hints** to ~50 functions across the codebase (~72% typing coverage)
- **Narrowed exception handling** — replaced 13 broad `except Exception:` clauses with specific types
- **Fixed nested functions** — all nested function definitions extracted to module level
- **Added disk caching** for repo tool directories and memory file data alongside session data
- **Extended data source discovery** — Repo Configs tab now queries OpenCode SQLite DB and Antigravity brain directory for repo/session counts

The result: a codebase that's more modular, faster-loading on repeat visits, easier to maintain, and fully type-safe — all verified through browser-based smoke tests with zero regressions.

## Notes

- Cost estimates are approximate based on published API pricing
- Cache token pricing uses reduced rates where available
- Only parses coding sessions — not Claude chat/cowork conversations
- The first page load after starting the app may take 30+ seconds to parse all session sources; subsequent navigation is instant thanks to disk caching
