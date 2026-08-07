"""Inspect open Orca terminals and their contents.

Wraps the read-only `orca` CLI (orca terminal list/show/read) so any agent with
access to this repo can see what Orca terminals are currently open and what's
inside them. Exposed three ways:
  - `python3 -m claude_analyzer.orca_terminals`
  - `claude-analyze --orca-terminals`
  - `orca-terminals`  (console script, after `pip install -e .`)
No state is changed. Stdlib only.
"""

import argparse
import json
import signal
import subprocess
import sys
import time

ORCA_BIN = "orca"

CONTENT_TAIL_DEFAULT = 40
READ_TIMEOUT = 15


class OrcaUnavailableError(RuntimeError):
    """The `orca` CLI is not installed / not on PATH."""


def _run_orca(args, timeout=READ_TIMEOUT):
    """Run `orca ... --json` and return the parsed `result` object.

    Raises OrcaUnavailableError if the CLI is missing, RuntimeError on a non-ok
    response (the error detail is included in the message).
    """
    try:
        proc = subprocess.run(
            [ORCA_BIN, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise OrcaUnavailableError(
            "orca CLI not found on PATH. Install Orca so `orca` is available."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"orca timed out after {timeout}s") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"orca exited {proc.returncode}: {detail[:300]}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"orca returned non-JSON output: {proc.stdout[:200]!r}"
        )

    if not isinstance(data, dict) or data.get("ok") is False:
        msg = data.get("error") if isinstance(data, dict) else "unknown error"
        raise RuntimeError(f"orca command failed: {msg}")

    return data.get("result", {})


def status():
    """Return the Orca runtime status dict (app running, runtime state, ...)."""
    return _run_orca(["status", "--json"])


def list_terminals(worktree=None):
    """List open Orca terminals.

    Returns a list of terminal dicts (handle, title, worktreePath, branch,
    connected, writable, lastOutputAt, preview, ...). `worktree` is an Orca
    selector like "active" or "id:<id>" to scope the listing.
    """
    args = ["terminal", "list", "--json"]
    if worktree:
        args += ["--worktree", worktree]
    result = _run_orca(args)
    terminals = result.get("terminals", []) if isinstance(result, dict) else []
    return terminals or []


def show_terminal(handle):
    """Return full details for a single terminal by handle."""
    result = _run_orca(["terminal", "show", "--terminal", handle, "--json"])
    return result.get("terminal", {}) if isinstance(result, dict) else {}


def read_terminal(handle, limit=CONTENT_TAIL_DEFAULT, cursor=None):
    """Read the content tail for a terminal.

    `limit` is the max number of lines returned. `cursor` enables paging for
    long buffers (follow oldestCursor/nextCursor while `limited` is true and
    nextCursor != latestCursor, per the orca-cli skill). Returns the `terminal`
    portion of the response (handle, status, tail, truncated, limited, cursors).
    """
    args = [
        "terminal", "read", "--terminal", handle,
        "--limit", str(limit), "--json",
    ]
    if cursor:
        args += ["--cursor", cursor]
    result = _run_orca(args)
    return result.get("terminal", {}) if isinstance(result, dict) else {}


def _preview_tail(preview, limit):
    """Turn a `terminal list` preview string into a bounded list of lines."""
    if not preview:
        return []
    if isinstance(preview, list):
        lines = preview
    else:
        lines = str(preview).split("\n")
    if limit:
        return lines[-limit:]
    return lines[-CONTENT_TAIL_DEFAULT:]


def _gather(terminals, limit):
    """Normalize a list of terminal dicts into display-ready records.

    Reads each terminal's content tail + status via `orca terminal read`; falls
    back to the `preview` field from `terminal list` when a read is unavailable.
    """
    out = []
    for t in terminals:
        handle = t.get("handle")
        status_v = None
        truncated = None
        limited = None
        tail = []
        try:
            read = read_terminal(handle, limit=limit)
            tail = read.get("tail") or []
            status_v = read.get("status")
            truncated = read.get("truncated")
            limited = read.get("limited")
        except RuntimeError:
            tail = []
        if not tail:
            tail = _preview_tail(t.get("preview"), limit)
        out.append({
            "handle": handle,
            "title": t.get("title"),
            "worktreePath": t.get("worktreePath"),
            "branch": _branch(t.get("branch") or ""),
            "connected": t.get("connected"),
            "writable": t.get("writable"),
            "status": status_v,
            "lastOutputAt": t.get("lastOutputAt"),
            "tail": tail,
            "truncated": truncated,
            "limited": limited,
        })
    return out


def _orca_unavailable_lines():
    return [
        "orca CLI not found.",
        "Install Orca so the `orca` command is on your PATH, then rerun.",
    ]


def _header(count):
    return f"Orca terminals ({count} open):"


def _footer(count):
    return f"({count} terminal{'s' if count != 1 else ''})"


def _fmt_ts(epoch_ms):
    try:
        return time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(int(epoch_ms) / 1000)
        )
    except (ValueError, TypeError, OSError):
        return "?"


def _branch(branch):
    if not branch:
        return ""
    return branch.replace("refs/heads/", "").replace("refs/tags/", "")


def _term_mark(yes):
    return "true" if yes else "false"


def _terminal_block(t, limit):
    title = t.get("title") or "(no title)"
    branch = _branch(t.get("branch") or "")
    head = f"[{branch}] {title}" if branch else title
    lines = [
        "┌─ " + head,
        f"  handle: {t.get('handle') or '?'}",
    ]
    worktree_path = t.get("worktreePath")
    if worktree_path:
        lines.append(f"  worktree: {worktree_path}")
    status = t.get("status")
    lines.append(
        f"  connected: {_term_mark(t.get('connected'))}  writable: "
        f"{_term_mark(t.get('writable'))}  status: {status or 'unknown'}"
    )
    lines.append(f"  last output: {_fmt_ts(t.get('lastOutputAt'))}")
    lines.append("")
    tail = t.get("tail") or []
    if not tail:
        tail = ["(no output captured)"]
    lines.extend("  " + (line.rstrip() if line else "") for line in tail[-limit:])
    return "\n".join(lines)


def summarize_terminals(limit=CONTENT_TAIL_DEFAULT, terminal=None):
    """Return (lines, ok) for a human-readable summary of open terminals."""
    try:
        status_info = status()
    except (OrcaUnavailableError, RuntimeError):
        return (_orca_unavailable_lines(), False)
    app = status_info.get("app", {}) if isinstance(status_info, dict) else {}
    if app and not app.get("running"):
        return (["Orca is not running (no open terminals)."], True)

    try:
        terminals = list_terminals()
    except RuntimeError as exc:
        return ([f"Failed to list terminals: {exc}"], False)

    if terminal:
        terminals = [t for t in terminals if t.get("handle") == terminal]
        if not terminals:
            return ([f"No open terminal with handle '{terminal}'."], True)

    gathered = _gather(terminals, limit)
    lines = [_header(len(gathered))]
    for t in gathered:
        lines.append("")
        lines.append(_terminal_block(t, limit))
        if t.get("limited"):
            lines.append("  (output truncated — more below; raise with --limit N)")
    lines.append("")
    lines.append(_footer(len(gathered)))
    return (lines, True)


def report(limit=CONTENT_TAIL_DEFAULT, terminal=None):
    """Return a human-readable string summary of open Orca terminals."""
    lines, _ok = summarize_terminals(limit=limit, terminal=terminal)
    return "\n".join(lines)


def report_json(limit=CONTENT_TAIL_DEFAULT, terminal=None):
    """Return a JSON string describing open Orca terminals."""
    try:
        status_info = status()
    except (OrcaUnavailableError, RuntimeError) as exc:
        return json.dumps({"ok": False, "error": str(exc), "terminals": []})

    app = status_info.get("app", {}) if isinstance(status_info, dict) else {}
    if app and not app.get("running"):
        return json.dumps({"ok": True, "running": False, "count": 0, "terminals": []})

    try:
        terminals = list_terminals()
    except RuntimeError as exc:
        return json.dumps({"ok": False, "error": str(exc), "terminals": []})

    if terminal:
        terminals = [t for t in terminals if t.get("handle") == terminal]

    gathered = _gather(terminals, limit)
    return json.dumps({
        "ok": True,
        "running": bool(app.get("running")) if app else True,
        "count": len(gathered),
        "terminals": gathered,
    }, indent=2)


def _build_cli_parser():
    parser = argparse.ArgumentParser(
        prog="orca-terminals",
        description="List open Orca terminals and what's inside them.",
    )
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable JSON output")
    parser.add_argument("--limit", type=int, default=CONTENT_TAIL_DEFAULT,
                        help="Max content lines per terminal (default: 40)")
    parser.add_argument("--terminal", metavar="HANDLE",
                        help="Inspect a single terminal by handle")
    return parser


def main(argv=None):
    # SIGPIPE: when stdout is piped to a truncating consumer (e.g. `| head`),
    # let the default handler terminate us cleanly instead of a late
    # BrokenPipeError during interpreter shutdown.
    if hasattr(signal, "SIGPIPE"):
        try:
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        except (ValueError, OSError):
            pass
    args = _build_cli_parser().parse_args(argv)
    try:
        if args.json:
            print(report_json(limit=args.limit, terminal=args.terminal))
        else:
            print(report(limit=args.limit, terminal=args.terminal))
    except BrokenPipeError:
        # Downstream consumer (e.g. `head`) closed the pipe early.
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(1)

    # Non-zero exit only when the orca CLI itself is unavailable.
    try:
        status()
    except OrcaUnavailableError:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
