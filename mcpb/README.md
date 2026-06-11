# fred-mcp — MCPB desktop-extension bundle

This directory builds the **[MCPB](https://github.com/modelcontextprotocol/mcpb)**
(`.mcpb`) bundle for one-click install in Claude Desktop / Claude Code, and for
submission to Anthropic's Connectors Directory.

## Why `type: "uv"` (not a vendored bundle)

fred depends on `pydantic`, whose `pydantic-core` is a **compiled, platform-specific**
wheel — MCPB explicitly *"cannot portably bundle compiled dependencies."* So this is a
**`uv`-type** bundle: it ships the **source + `pyproject.toml`** (no vendored `server/lib`),
and the host's `uv` installs the correct-platform dependencies at install time. That keeps it
cross-platform (`darwin` / `win32` / `linux`). The API key is collected via `user_config`
(marked `sensitive` — Claude Desktop stores it in the OS keychain) and passed to the server
as `FRED_API_KEY`.

> Note: MCPB's `uv` runtime is officially **experimental**. Some Claude Desktop builds may
> require a system Python to be present even when `uv` is installed
> ([mcpb#84](https://github.com/modelcontextprotocol/mcpb/issues/84)) — verify on the target
> Claude Desktop version before relying on it.

## Build

Requires the `mcpb` CLI: `npm i -g @anthropic-ai/mcpb`.

```bash
./build.sh        # validates manifest.json, stages source + pyproject, packs the .mcpb
```

Output: `../dist/mcpwright-fred-<version>.mcpb` (gitignored). The build stages only the files
the bundle needs (`manifest.json`, `icon.png`, `pyproject.toml`, `README.md`, `LICENSE`,
`uv.lock`, `src/`) — never tests, caches, or a venv — and guards the version lockstep between
`manifest.json` and `pyproject.toml`.

## Install (end user)

Download the `.mcpb` from the [latest release](https://github.com/mcpwright/fred-mcp/releases),
double-click it (or drag into Claude Desktop → Settings → Extensions), and paste your free
FRED API key when prompted (get one at
https://fred.stlouisfed.org/docs/api/api_key_request.html).

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve
Bank of St. Louis.
