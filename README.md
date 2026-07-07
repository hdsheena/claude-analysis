# claude-analysis

Analyze your Claude Code session history for insights, usage patterns, and cost tracking.

Parses JSONL session data from `~/.claude/projects/` and the Claude Desktop app's local agent mode sessions to give you a comprehensive picture of your AI coding activity.

## Quick Start

```bash
cd ~/GitHub/claude-analysis
python3 analyze.py
```

No dependencies beyond Python 3.9+ standard library.

## Commands

```bash
python3 analyze.py                 # Full summary report (default)
python3 analyze.py --projects      # Per-project breakdown
python3 analyze.py --models        # Model usage details
python3 analyze.py --tools         # Tool usage breakdown
python3 analyze.py --sessions      # List top 20 sessions
python3 analyze.py --sessions 50   # List top 50 sessions
python3 analyze.py --project evc   # Filter by project name
python3 analyze.py --source local-agent  # Only local agent sessions
python3 analyze.py --all           # Show everything
python3 analyze.py --json          # Output as JSON
```

## What It Shows

- **Overview**: total sessions, messages, disk usage
- **Tokens**: input/output, cache read/write, cache hit ratio
- **Cost**: estimated spend by model
- **Models**: distribution and per-model token breakdown
- **Projects**: sessions per project, size per project, tokens per project
- **Tools**: most-used tools (Bash, Edit, Read, etc.)
- **Sessions**: list of sessions sorted by complexity
- **Behavior patterns**: stop reasons, message types, session length distribution

## Data Sources

| Source | Path |
|--------|------|
| CLI sessions | `~/.claude/projects/` |
| Desktop agent sessions | `~/Library/Application Support/Claude/local-agent-mode-sessions/` |
| Session registry | `~/.claude/sessions/` |

## Notes

- Cost estimates are approximate based on published API pricing
- Cache token pricing uses reduced rates where available
- Only parses Claude Code coding sessions — not Claude chat/cowork conversations
