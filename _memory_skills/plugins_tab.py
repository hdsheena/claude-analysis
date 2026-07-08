"""Plugins tab — display installed plugins and marketplaces."""

import os
import glob
import json
import pandas as pd
import streamlit as st


def render() -> None:
    """Display installed plugins and marketplaces from ~/.claude/plugins."""
    st.subheader("🔌 Installed Plugins & Marketplaces")
    plugins_dir = os.path.expanduser("~/.claude/plugins")

    if not os.path.isdir(plugins_dir):
        st.info("No plugins directory found at ~/.claude/plugins")
        return

    st.caption("**Configuration files:**")
    for cfg in ["known_marketplaces.json", "blocklist.json"]:
        path = os.path.join(plugins_dir, cfg)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    st.caption(f"  • **{cfg}**: {len(data)} entries")
                elif isinstance(data, dict):
                    st.caption(f"  • **{cfg}**: {len(data)} keys")
            except (OSError, json.JSONDecodeError):
                st.caption(f"  • **{cfg}**: (parse error)")

    marketplaces_dir = os.path.join(plugins_dir, "marketplaces")
    if os.path.isdir(marketplaces_dir):
        st.divider()
        st.subheader("🏪 Marketplaces")
        for mp in sorted(os.listdir(marketplaces_dir)):
            mp_path = os.path.join(marketplaces_dir, mp)
            if os.path.isdir(mp_path):
                plugins_path = os.path.join(mp_path, "plugins")
                external_path = os.path.join(mp_path, "external_plugins")
                plugin_count = len(os.listdir(plugins_path)) if os.path.isdir(plugins_path) else 0
                ext_count = len(os.listdir(external_path)) if os.path.isdir(external_path) else 0
                with st.expander(
                    f"**{mp}** — {plugin_count} plugins, {ext_count} external",
                    expanded=plugin_count + ext_count < 20,
                ):
                    if os.path.isdir(plugins_path):
                        st.caption("Plugins:")
                        for plugin in sorted(os.listdir(plugins_path))[:10]:
                            st.caption(f"  • {plugin}")
                        if plugin_count > 10:
                            st.caption(f"  ... and {plugin_count - 10} more")
                    if os.path.isdir(external_path) and ext_count > 0:
                        st.caption("External:")
                        for plugin in sorted(os.listdir(external_path))[:5]:
                            st.caption(f"  • {plugin}")
                        if ext_count > 5:
                            st.caption(f"  ... and {ext_count - 5} more")

    manifests = glob.glob(os.path.join(plugins_dir, "**", "manifest.json"), recursive=True)
    manifests = [m for m in manifests if "marketplaces" not in m]
    if manifests:
        st.divider()
        st.subheader("📦 Installed Plugin Manifests")
        manifest_data = []
        for m in manifests[:20]:
            rel = m.replace(plugins_dir, "").lstrip("/")
            try:
                with open(m) as f:
                    d = json.load(f)
                manifest_data.append({"Name": d.get("name", "?"), "Version": d.get("version", "?"), "Path": rel})
            except (OSError, json.JSONDecodeError):
                manifest_data.append({"Name": "?", "Version": "?", "Path": rel})
        st.dataframe(pd.DataFrame(manifest_data), use_container_width=True, hide_index=True)
    else:
        st.caption("No installed plugin manifests found.")
