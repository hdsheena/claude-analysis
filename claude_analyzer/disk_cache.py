"""SQLite-based session cache with gzip compression.

Stores per-source session lists in a single SQLite database at .cache/sessions.db.
Each source gets its own row — no more single huge blob. Invalidates when:
- The cache entry is older than CACHE_TTL seconds
- The source data has been modified more recently than the cache entry
"""

import gzip
import os
import pickle
import sqlite3
import glob
import time

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
CACHE_PATH = os.path.join(CACHE_DIR, "sessions.db")
CACHE_TTL = 86400  # 24 hours


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Clean up old pickle files from previous cache format
    for f in glob.glob(os.path.join(CACHE_DIR, "*.pkl")):
        try:
            os.remove(f)
        except OSError:
            pass

    conn = sqlite3.connect(CACHE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "  key TEXT PRIMARY KEY,"
        "  data BLOB,"
        "  created_at REAL"
        ")"
    )
    # Clean up stale keys from the old 5-source format
    conn.execute(
        "DELETE FROM cache WHERE key IN ("
        "  'sessions_projects', 'sessions_local-agent'"
        ")"
    )
    conn.commit()
    conn.close()


def _newest_source_mtime(source: str) -> float:
    """Return the mtime of the newest source file relevant to the given source."""
    newest = 0.0

    if source in ("claude", "projects"):
        root = os.path.expanduser("~/.claude/projects")
        for f in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            try:
                newest = max(newest, os.path.getmtime(f))
            except OSError:
                pass

    if source in ("claude", "local-agent"):
        root = os.path.expanduser(
            "~/Library/Application Support/Claude/local-agent-mode-sessions"
        )
        for f in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            try:
                newest = max(newest, os.path.getmtime(f))
            except OSError:
                pass

    if source == "freebuff":
        fb_dir = os.path.expanduser("~/.config/manicode/projects")
        for f in glob.glob(
            os.path.join(fb_dir, "**", "chat-messages.json"), recursive=True
        ):
            try:
                newest = max(newest, os.path.getmtime(f))
            except OSError:
                pass

    elif source == "mimo":
        mimo_db = os.path.expanduser("~/.local/share/mimocode/mimocode.db")
        try:
            newest = max(newest, os.path.getmtime(mimo_db))
        except OSError:
            pass

    elif source == "opencode":
        oc_db = os.path.expanduser("~/.local/share/opencode/opencode.db")
        try:
            newest = max(newest, os.path.getmtime(oc_db))
        except OSError:
            pass

    return newest


def cache_get(key: str):
    """Return cached data or None if not cached, stale, or source data is newer."""
    _ensure_cache()

    try:
        conn = sqlite3.connect(CACHE_PATH)
        row = conn.execute(
            "SELECT data, created_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return None

    if not row:
        return None

    data_blob, created_at = row

    # TTL check
    if time.time() - created_at > CACHE_TTL:
        return None

    # Source freshness check
    source = key.replace("sessions_", "")
    if source not in ("all",):
        source_mtime = _newest_source_mtime(source)
        if source_mtime > created_at:
            return None

    # Decompress and unpickle
    try:
        return pickle.loads(gzip.decompress(data_blob))
    except (gzip.BadGzipFile, pickle.UnpicklingError, EOFError):
        return None


def cache_set(key: str, data):
    """Write data to the cache (gzip-compressed pickle)."""
    _ensure_cache()

    try:
        blob = gzip.compress(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL))
    except (pickle.PicklingError, OSError):
        return

    try:
        conn = sqlite3.connect(CACHE_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, data, created_at) VALUES (?, ?, ?)",
            (key, blob, time.time()),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def cache_clear():
    """Remove all rows from the cache table and delete old pickle files."""
    _ensure_cache()

    try:
        conn = sqlite3.connect(CACHE_PATH)
        conn.execute("DELETE FROM cache")
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass

    # Clean up old pickle files from previous cache format
    for f in glob.glob(os.path.join(CACHE_DIR, "*.pkl")):
        try:
            os.remove(f)
        except OSError:
            pass


def cache_info() -> dict:
    """Return info about the cache for display."""
    _ensure_cache()

    try:
        conn = sqlite3.connect(CACHE_PATH)
        rows = conn.execute(
            "SELECT key, LENGTH(data), created_at FROM cache"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return {"count": 0, "size_bytes": 0, "newest_ts": None}

    total_size = sum(r[1] for r in rows) if rows else 0
    newest = max(r[2] for r in rows) if rows else None

    return {
        "count": len(rows),
        "size_bytes": total_size,
        "dir": CACHE_DIR,
        "newest_ts": newest,
        "db_path": CACHE_PATH,
    }
