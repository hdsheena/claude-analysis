"""Shared cached data loaders and sidebar for the Streamlit app.

Import this module from both app.py and pages/ to avoid circular imports.
"""

import time
import threading
import streamlit as st

from claude_analyzer.parser import parse_sessions, parse_sessions_parallel, enrich_sessions
from claude_analyzer.stats import AggStats, compute_stats
from claude_analyzer.disk_cache import cache_get, cache_set, cache_info, cache_clear


TIME_RANGES = {
    "All time": None,
    "Last week": 7 * 24 * 3600,
    "Last month": 30 * 24 * 3600,
    "Last 3 months": 90 * 24 * 3600,
    "Last 6 months": 180 * 24 * 3600,
    "Last year": 365 * 24 * 3600,
}

ALL_SOURCES = ["claude", "freebuff", "mimo", "opencode", "antigravity"]

_SOURCE_TO_CACHE_KEY = {
    "projects": "claude", "local-agent": "claude",
    "freebuff": "freebuff", "mimo": "mimo", "opencode": "opencode",
    "antigravity": "antigravity",
}

_SIDEBAR_CSS = """
<style>
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #2a2a4a;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    [data-testid="stMetric"] label {
        color: #8888aa !important;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    [data-testid="stMetricValue"] {
        color: #e0e0ff !important;
        font-size: 1.6rem;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f0f23 0%, #1a1a2e 100%);
        border-right: 1px solid #2a2a4a;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #2a2a4a;
        border-radius: 8px;
    }
    [data-testid="stSidebarNav"] {
        display: none;
    }
</style>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Session loading
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400, show_spinner="Loading sessions...")
def load_sessions(source: str = "all") -> list:
    """Load and enrich all sessions (disk + memory cached).

    Caches per-source in SQLite so switching sources is instant.
    For 'all', loads and merges individual source caches.
    On first load (cache miss), uses parallel parsing for 'all' to cut
    parse time from ~16s to ~5s.
    """
    sources = ALL_SOURCES if source == "all" else [source]

    if source == "all":
        # Try per-source caches first
        cached = {}
        missing = []
        for src in sources:
            data = cache_get(f"sessions_{src}")
            if data is not None:
                cached[src] = data
            else:
                missing.append(src)

        if not missing:
            all_sessions = []
            for src in sources:
                all_sessions.extend(cached[src])
            return all_sessions

        if len(missing) >= 2:
            sessions = parse_sessions_parallel("all")
            enrich_sessions(sessions)
            by_source = {s: [] for s in sources}
            for s in sessions:
                key = _SOURCE_TO_CACHE_KEY.get(s.source)
                if key:
                    by_source[key].append(s)
            for src in sources:
                cache_set(f"sessions_{src}", by_source[src])
            return sessions

    # Individual source or partial cache fallback
    all_sessions = []
    for src in sources:
        cache_key = f"sessions_{src}"
        data = cache_get(cache_key)
        if data is not None:
            all_sessions.extend(data)
        else:
            sessions = parse_sessions(source=src)
            enrich_sessions(sessions)
            cache_set(cache_key, sessions)
            all_sessions.extend(sessions)

    return all_sessions


@st.cache_data(ttl=86400, show_spinner="Computing statistics...")
def get_stats(_sessions) -> AggStats:
    """Compute aggregate stats from sessions (cached)."""
    return compute_stats(_sessions)


# ═══════════════════════════════════════════════════════════════════════════════
# Filters
# ═══════════════════════════════════════════════════════════════════════════════

def filter_sessions(sessions, project_filter: str = "") -> list:
    """Filter sessions by project name substring."""
    if not project_filter:
        return sessions
    return [s for s in sessions if project_filter.lower() in s.project.lower()]


def filter_by_time(sessions, time_range: str = "All time") -> list:
    """Filter sessions by a time range.

    Sessions without a started_at timestamp are always included.
    """
    max_age = TIME_RANGES.get(time_range)
    if max_age is None:
        return sessions

    cutoff = time.time() - max_age
    filtered = []
    for s in sessions:
        ts = s.started_at
        if ts is None:
            filtered.append(s)
            continue
        if ts > 1e12:
            ts = ts / 1000.0
        if ts >= cutoff:
            filtered.append(s)
    return filtered


def apply_all_filters(sessions, project_filter: str = "", time_range: str = "All time") -> list:
    """Apply both project and time filters in one pass."""
    sessions = filter_by_time(sessions, time_range)
    sessions = filter_sessions(sessions, project_filter)
    return sessions


def get_time_range_index() -> int:
    """Get the index for a time_range selectbox, synced from session_state."""
    key = st.session_state.get("time_range", "All time")
    keys = list(TIME_RANGES.keys())
    return keys.index(key) if key in keys else 0


# ═══════════════════════════════════════════════════════════════════════════════
# Cache prewarming
# ═══════════════════════════════════════════════════════════════════════════════

def _prewarm_cache_sync() -> None:
    """Parse and cache all missing sources synchronously.

    Called after cache_clear() so the next page load after refresh
    gets cache HITs instead of waiting for a full re-parse.
    """
    try:
        missing = [src for src in ALL_SOURCES if cache_get(f"sessions_{src}") is None]
        if not missing:
            return
        all_parsed = []
        for src in missing:
            s = parse_sessions(source=src)
            enrich_sessions(s)
            all_parsed.extend(s)
        by_source = {s: [] for s in ALL_SOURCES}
        for s in all_parsed:
            key = _SOURCE_TO_CACHE_KEY.get(s.source)
            if key:
                by_source[key].append(s)
        for src in ALL_SOURCES:
            if cache_get(f"sessions_{src}") is None:
                cache_set(f"sessions_{src}", by_source[src])
    except Exception:
        pass


def _prewarm_caches_async() -> None:
    """Parse and cache all sources in a background thread."""
    t = threading.Thread(target=_prewarm_cache_sync, daemon=True)
    t.start()


# ═══════════════════════════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════════════════════════

def _render_nav_links() -> None:
    """Render page navigation links in the sidebar."""
    st.divider()
    st.caption("📊 PAGES")
    st.page_link("app.py", label="🏠 Summary", icon="📋")
    st.page_link("pages/1_Timeline.py", label="🗓️ Timeline", icon="📈")
    st.page_link("pages/2_Projects.py", label="📁 Projects", icon="📂")
    st.page_link("pages/3_Sessions.py", label="🔍 Sessions & Raw Data", icon="💬")
    st.page_link("pages/4_Compare.py", label="⚖️ Compare", icon="🔀")
    st.page_link("pages/5_Memory_Skills.py", label="📝 Memory & Skills", icon="🔧")
    st.page_link("pages/6_Antigravity.py", label="🧠 Antigravity", icon="💭")


def _render_cache_status() -> None:
    """Show disk cache age and size in sidebar."""
    ci = cache_info()
    if ci["count"] == 0:
        return
    age = "just now"
    if ci["newest_ts"]:
        seconds = int(time.time() - ci["newest_ts"])
        if seconds < 60:
            age = f"{seconds}s ago"
        elif seconds < 3600:
            age = f"{seconds // 60}m ago"
        else:
            age = f"{seconds // 3600}h ago"
    st.caption(
        f"💾 Disk cache: {ci['count']} source"
        f"{'' if ci['count'] == 1 else 's'}"
        f" ({ci['size_bytes'] / 1024:.0f} KB) · {age}"
    )


def render_sidebar() -> tuple:
    """Render the shared sidebar with filters, nav, cache status, and refresh.

    Must be called once per page. Returns (source, project_filter, time_range).
    """
    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)

    with st.sidebar:
        st.title("🔬 Claude Analytics")

        source = st.selectbox(
            "Session source",
            options=["all", "claude", "freebuff", "mimo", "opencode", "antigravity"],
            index=0,
            key="sidebar_source",
            help="Filter by where sessions are stored",
        )
        st.session_state["source"] = source

        project_filter = st.text_input(
            "Project filter",
            placeholder="e.g., evc or ia",
            key="sidebar_project",
            help="Substring match on project name",
        )
        st.session_state["project_filter"] = project_filter

        time_range = st.selectbox(
            "Time range",
            options=list(TIME_RANGES.keys()),
            index=get_time_range_index(),
            key="sidebar_time_range",
            help="Filter sessions by time period",
        )
        st.session_state["time_range"] = time_range

        if st.button("🔄 Refresh data", use_container_width=True):
            st.cache_data.clear()
            cache_clear()
            _prewarm_caches_async()
            st.rerun()

        _render_cache_status()
        _render_nav_links()

        st.divider()
        st.caption("Claude Analyzer v0.1.0")

    return source, project_filter, time_range
