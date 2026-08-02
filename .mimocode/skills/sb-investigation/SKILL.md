---
name: sb-investigation
description: Investigate Azure Service Bus queue health, run adaptive/safe-batch scripts, and diagnose disposition issues in evc-tools
---

# Service Bus Investigation Workflow

Standard procedure for investigating Azure Service Bus queues, running diagnostic scripts, and resolving disposition issues.

## When to use

- Queue messages are backing up or failing
- Need to check current SB state before running a batch
- Diagnosing why messages are stuck in a specific disposition
- User asks to "run the SB scripts" or "check the queues"

## Prerequisites

- Python venv at `evc-tools/.venv`
- `.env` file with `SERVICE_BUS_CONNECTION_STRING` and related keys
- Scripts in `evc-tools/courtenay py scripts/azure_scripts/`

## Workflow

### 1. Activate environment and check current state

```bash
source /Users/m4mbp/Documents/GitHub/evc-tools/.venv/bin/activate
set -a && source .env && set +a
cd "/Users/m4mbp/Documents/GitHub/evc-tools/courtenay py scripts/azure_scripts"
```

### 2. Run adaptive diagnostics

```bash
/Users/m4mbp/Documents/GitHub/evc-tools/.venv/bin/python sb_adaptive_run.py
```

This checks queue depths, message ages, and error rates. Output shows per-queue health.

### 3. Check governor runtime

```bash
/Users/m4mbp/Documents/GitHub/evc-tools/.venv/bin/python -c "
from sb_lib.governor_runtime import check_governor
check_governor()
"
```

If governor is throttling, wait until it clears before proceeding.

### 4. Analyze disposition

```bash
/Users/m4mbp/Documents/GitHub/evc-tools/.venv/bin/python -c "
from sb_lib.disposition import analyze_disposition
analyze_disposition()
"
```

Check for messages stuck in error/retry states.

### 5. Run safe batch (if governor allows)

```bash
/Users/m4mbp/Documents/GitHub/evc-tools/.venv/bin/python sb_safe_batch_run.py
```

Only run if governor check passed and disposition looks healthy.

### 6. Commit changes (if scripts were edited)

```bash
cd "/Users/m4mbp/Documents/GitHub/evc-tools"
git add "courtenay py scripts/azure_scripts/sb_lib/"
git commit -m "fix: <description of change>"
```

## Key files

- `sb_lib/disposition.py` — Queue disposition analysis and cleanup logic
- `sb_lib/governor_runtime.py` — Rate limiting and throttle checks
- `sb_lib/loader.py` — Message loading and batch preparation
- `sb_adaptive_run.py` — Main diagnostic entry point
- `sb_safe_batch_run.py` — Safe batch execution with guardrails

## Gotchas

- Governor must be checked BEFORE running batch — running while throttled causes cascading failures
- Disposition analysis may take 30-60s for large queues
- Always activate venv and source .env before running any script
- Scripts use `psycopg2` for DB access — ensure connection string is in .env
