"""Page: Memory & Skills — Memory files, skills, plugins, and repo config analysis."""

import streamlit as st

st.set_page_config(
    page_title="Memory & Skills - Claude Analytics",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

from shared import render_sidebar
from _memory_skills import memory_tab, skills_tab, plugins_tab, data_sources_tab, repo_configs_tab


# ═══════════════════════════════════════════════════════════════════════════════
# Page entry point
# ═══════════════════════════════════════════════════════════════════════════════

st.title("📝 Memory, Skills & Plugins")

_, _, _ = render_sidebar()

tab_memory, tab_skills, tab_plugins, tab_repo, tab_sources = st.tabs(
    ["📝 Memory Files", "🔧 Skills", "🔌 Plugins", "🗂️ Repo Configs", "📂 Data Sources"]
)

with tab_memory:
    memory_tab.render()

with tab_skills:
    skills_tab.render()

with tab_plugins:
    plugins_tab.render()

with tab_sources:
    data_sources_tab.render()

with tab_repo:
    repo_configs_tab.render()
