# Searching Local Agent Sessions for Keywords

How to find sessions across **all** local agent sources that mention a keyword
(`wwwroot`, `kudu`, `odr`, …) and were active after a reference timestamp.

Proven on 2026-08-02: found every real session mentioning `wwwroot`/`kudu`
across Claude, Freebuff, Antigravity, OpenCode, and Mimo, while filtering out
~12 base64-noise false positives.

## The core idea

Three things make this search work:

1. **Every source is auto-discovered from its hardcoded path** — no manual
   import step. The paths are the same ones the dashboard uses (see
   `claude_analyzer/parser.py:19-29`).
2. **"After this time" = last activity after the cutoff.** For Claude JSONL /
   Freebuff / Antigravity the file **mtime** is the best proxy for last
   activity (JSONL files are appended during the session). For OpenCode/Mimo,
   use the session's `time_updated` column (epoch **milliseconds** — divide by
   1000 before comparing).
3. **Two-pass match.** Pass 1: distinctive-keyword grep/LIKE to find candidate
   files/sessions. Pass 2: word-boundary regex to confirm and extract
   snippets.

## The trap that makes naive searches wrong

`odr` (and even `kudu`) appear inside **base64-encoded / encrypted tool
output** as random substrings (e.g. `...kUDU...`, `...odr...`). A plain
`rg odr` or SQL `LIKE '%odr%'` matches dozens of sessions that contain **no
real mention**. So:

- Use `\b` word boundaries for the *display* regex.
- Expect SQL `LIKE '%odr%'` hits to be mostly noise; verify every hit by
  printing the surrounding snippet before trusting it.

## Source inventory

| Source | Where it lives | Last-activity signal |
|---|---|---|
| Claude projects | `~/.claude/projects/*/*.jsonl` | file mtime |
| Claude local-agent | `~/Library/Application Support/Claude/local-agent-mode-sessions/**/audit.jsonl` | file mtime |
| Session registry | `~/.claude/sessions/*.json` (metadata only, not content) | `startedAt` (start, not activity) |
| OpenCode | `~/.local/share/opencode/opencode.db` (SQLite) | `session.time_updated` (ms) |
| Mimo | `~/.local/share/mimocode/mimocode.db` (SQLite) | `session.time_updated` (ms) |
| Freebuff | `~/.config/manicode/projects/*/chats/*/chat-messages.json` | file mtime |
| Antigravity | `~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl` | file mtime |

## Step 1 — compute the cutoff epoch

```bash
python3 -c "
from datetime import datetime, timezone
dt = datetime.fromisoformat('2026-07-27T18:59:29').replace(tzinfo=timezone.utc)
print(int(dt.timestamp()))   # 1785178769
"
```

## Step 2 — prefilter candidates (fast)

Distinctive keywords first (skip `odr` here — too noisy):

```bash
rg -l -i "wwwroot|kudu" \
  "$HOME/.claude/projects" \
  "$HOME/Library/Application Support/Claude/local-agent-mode-sessions" \
  "$HOME/.config/manicode/projects" \
  "$HOME/.gemini/antigravity/brain"
```

For the SQLite sources, `data` is a JSON blob column, so grep by hand:

```bash
python3 -c "
import sqlite3
for db in ('$HOME/.local/share/opencode/opencode.db',
           '$HOME/.local/share/mimocode/mimocode.db'):
    conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
    for kw in ('wwwroot', 'kudu', 'odr'):
        for r in conn.execute(\"SELECT id, title FROM session WHERE title LIKE ? OR directory LIKE ?\",
                              ('%'+kw+'%', '%'+kw+'%')):
            print(kw, 'session', r['id'], r['title'])
        for m in conn.execute(\"SELECT id, session_id, data FROM message WHERE data LIKE ?\",
                              ('%'+kw+'%',)):
            print(kw, 'message', m['session_id'])
    conn.close()
"
```

## Step 3 — filter by last activity and confirm content

The full sweep (this is the script that produced the answer):

```python
import os, glob, sqlite3, re
from datetime import datetime, timezone

CUTOFF = 1785178769                          # from Step 1
KW = re.compile(r'(wwwroot|kudu|\bodr\b)', re.IGNORECASE)   # word-boundary display regex

def fmt(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if ts else '?'

def has_kw(text):
    return bool(KW.search(text or ''))

results = []

def scan_files(globpat, label, project_fn):
    for f in glob.glob(globpat, recursive='**' in globpat):
        try:
            mtime = os.path.getmtime(f)
        except OSError:
            continue
        if mtime <= CUTOFF:
            continue
        with open(f, encoding='utf-8', errors='replace') as fh:
            matched = any(has_kw(line) for line in fh)
        if matched:
            results.append((mtime, label, project_fn(f), os.path.basename(f)[:24], f, ''))

scan_files(os.path.expanduser('~/.claude/projects/*/*.jsonl'), 'claude',
           lambda f: os.path.basename(os.path.dirname(f)))
scan_files(os.path.expanduser('~/Library/Application Support/Claude/local-agent-mode-sessions/**/audit.jsonl'), 'local-agent',
           lambda f: 'local-agent')
scan_files(os.path.expanduser('~/.config/manicode/projects/*/chats/*/chat-messages.json'), 'freebuff',
           lambda f: f.split('/projects/')[1].split('/')[0])
scan_files(os.path.expanduser('~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl'), 'antigravity',
           lambda f: 'antigravity')

for db, label in [('~/.local/share/opencode/opencode.db', 'opencode'),
                  ('~/.local/share/mimocode/mimocode.db', 'mimo')]:
    path = os.path.expanduser(db)
    if not os.path.isfile(path):
        continue
    conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
    for r in conn.execute("SELECT id, title, directory, time_updated FROM session"):
        tupd = r['time_updated'] or 0
        tsec = tupd / 1000.0 if tupd > 1e12 else float(tupd or 0)   # ms -> seconds
        if tsec <= CUTOFF:
            continue
        title = r['title'] or ''
        matched = has_kw(title) or has_kw(r['directory'])
        if not matched:
            m = conn.execute("SELECT 1 FROM message WHERE session_id=? AND "
                             "(data LIKE '%wwwroot%' OR data LIKE '%kudu%' OR data LIKE '%odr%') LIMIT 1",
                             (r['id'],)).fetchone()
            matched = m is not None
        if matched:
            results.append((tsec, label, os.path.basename(r['directory'] or '') or 'unknown',
                            r['id'][:12], path, title[:80]))
    conn.close()

results.sort(key=lambda x: -x[0])
print(f'{len(results)} sessions with keyword AND activity after {fmt(CUTOFF)}')
for ts, src, proj, sid, path, note in results:
    print(f"{fmt(ts)}  [{src:<12}] {proj:<38} {sid}  {note}")
```

## Step 4 — extract the matching snippets (verify, don't trust)

For each hit, print ~200 chars of context around the first 1–2 matches so you
can separate real mentions from base64 noise:

```python
def snippet(text, before=50, after=120):
    m = KW.search(text or '')
    if not m:
        return ''
    s = max(0, m.start() - before)
    return text[s:m.end() + after].replace('\n', ' ').strip()

# files: iterate the matched files and print snippet(line) for each line
# that KW.search()s; DBs: SELECT data FROM message WHERE session_id=? AND
# data LIKE '%kw%' LIMIT 3, then print snippet(row['data'])
```

Real `wwwroot` matches look like `/home/site/wwwroot/app/...` paths; real
`kudu` matches mention the Kudu endpoint, `[Kudu-SourcePackageUriDownloadStep]`,
or `az functionapp log tail`. Base64 matches are long mixed-case alphanumeric
runs — discard them.

## Notes

- **Registry isn't content.** `~/.claude/sessions/*.json` holds metadata only
  (`sessionId`, `name`, `kind`, `cwd`, `startedAt`); search it for identity,
  never for message content.
- **`startedAt` vs last activity.** The registry gives you *start* times. The
  user's reference timestamps are *last activity* — hence mtime / `time_updated`.
- **The reference session may be gone.** Nothing on disk had lastActivityAt
  exactly `2026-07-27T18:59:29Z`; the cutoff still worked because the filter is
  `> cutoff`, not `==`.
- **Missed subagent content?** Claude writes subagent transcripts under
  `~/.claude/projects/<proj>/<session>/subagents/*.jsonl` and tool results under
  `<session>/tool-results/`. The `projects/*/*.jsonl` glob skips the one-level-deeper
  paths; add `projects/*/*/subagents/*.jsonl` (or `**/*.jsonl`) if you need them.
