"""Invariants between the MCPB manifest and the actual server."""

import asyncio
import json
import tomllib
from pathlib import Path

from fred_mcp.server import mcp

_ROOT = Path(__file__).parent.parent


def _manifest() -> dict:
    return json.loads((_ROOT / "mcpb" / "manifest.json").read_text())


def test_manifest_tools_match_server_tools():
    manifest_tools = {t["name"] for t in _manifest()["tools"]}
    server_tools = {t.name for t in asyncio.run(mcp.list_tools())}
    assert manifest_tools == server_tools


def test_manifest_version_locksteps_pyproject():
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    assert _manifest()["version"] == pyproject["project"]["version"]


def test_manifest_env_var_is_the_real_one():
    env = _manifest()["server"]["mcp_config"]["env"]
    assert set(env) == {"FRED_API_KEY"}
    assert "user_config.fred_api_key" in env["FRED_API_KEY"]


def test_manifest_privacy_policy_has_trailing_slash():
    # GitHub Pages 301s /privacy -> /privacy/; link the canonical URL directly.
    assert _manifest()["privacy_policies"] == ["https://mcpwright.com/privacy/"]
