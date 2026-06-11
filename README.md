# fred-mcp

<!-- mcp-name: io.github.mcpwright/fred-mcp -->

**FRED® economic data inside your AI agent — including what the numbers said
*before* the revisions.** An MCP server for the Federal Reserve Bank of
St. Louis's FRED® API: search and read 800,000+ U.S. and international time
series, follow the release calendar, and — the distinctive part — query
**ALFRED® vintage data**: any series exactly as it was known on a past date,
and any single data point's full revision history from its initial print to
today's value.

Read-only, built on public endpoints, powered by **your own free FRED API
key**. Live API calls with a volatility-aware cache (vintage reads are
immutable and cache long; current data stays fresh) — no bulk mirroring.

> This product uses the FRED® API but is not endorsed or certified by the
> Federal Reserve Bank of St. Louis. By using this server you agree to the
> [FRED® API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html).

**Status:** v0.1 — 9 tools, CI-gated, built on
[mcpwright-core](https://github.com/mcpwright/mcpwright-core).

## Why vintage data matters

Economic numbers get revised — sometimes dramatically. The *advance* estimate
of Q4-2008 real GDP told policymakers the economy was shrinking far more
slowly than the number that stands today. If an agent reasons about what
decision-makers knew *at the time* using *current* data, it is quietly wrong.
`get_series_as_of` and `get_revision_history` make as-published data a
first-class question.

## Tools

| Tool | What it does |
| --- | --- |
| `search_series` | Find series IDs by free text, best matches first |
| `get_series` | One series' full metadata + verbatim notes |
| `get_observations` | A date window of values; transforms (`pct_change_yoy`, …) + downsampling |
| `get_latest` | The most recent value + the next scheduled release date |
| `compare_series` | 2–5 series aligned on one date axis |
| `get_release_calendar` | Upcoming data releases ("when's the next jobs report?") |
| `get_series_as_of` ⭐ | A series exactly as known on a past date (ALFRED vintage) |
| `get_revision_history` ⭐ | One data point's life: initial print → every revision → today |
| `get_vintage_dates` ⭐ | When a series was released/revised; bounds the vintage tools |

All tools are read-only and annotated as such.

## Install

You need a **free FRED API key** (takes seconds):
<https://fred.stlouisfed.org/docs/api/api_key_request.html>. Keys are personal
under the FRED terms — bring your own.

### `uvx` (any MCP client)

```json
{
  "mcpServers": {
    "fred": {
      "command": "uvx",
      "args": ["mcpwright-fred"],
      "env": { "FRED_API_KEY": "your-key-here" }
    }
  }
}
```

### Claude Code

```bash
claude mcp add fred -e FRED_API_KEY=your-key-here -- uvx mcpwright-fred
```

### Claude Desktop

Use the one-click `.mcpb` extension from the
[latest release](https://github.com/mcpwright/fred-mcp/releases) (it prompts
for your API key), or add the `uvx` JSON above to your
`claude_desktop_config.json`.

### OpenAI Agents SDK / other clients

Any MCP-capable client works — point it at `uvx mcpwright-fred` over stdio
with `FRED_API_KEY` in the environment.

## Notes

- **Revisions:** current values often differ from what was originally
  published; for "what was known at the time", use the vintage tools.
- **Copyrighted series:** some FRED series are owned by third parties; their
  notes carry the owner's terms (surfaced verbatim, flagged via
  `copyrighted`). You are responsible for complying with them beyond personal
  use.
- **Caching & rate limits:** responses are cached in-memory (vintage reads
  long, live reads short) and requests are throttled well under FRED's rate
  limit. Set `FRED_MCP_CACHE=0` to disable caching, `FRED_MCP_USER_AGENT` to
  identify your own deployment.

## Develop

```bash
git clone https://github.com/mcpwright/fred-mcp && cd fred-mcp
uv sync
uv run pytest                                  # tests
uv run mypy                                    # types
uv run ruff check src/ && uv run ruff format --check src/   # lint + format
uv run pre-commit run --all-files              # everything, like CI
```

Dev loop: feature branch → PR → `Code Quality & Tests` green → squash-merge.

## Roadmap

- [x] v1 tool surface (9 tools incl. the ALFRED vintage lane)
- [ ] Publish to PyPI (`mcpwright-fred`) + the MCP Registry
- [ ] Site page at [mcpwright.com/fred](https://mcpwright.com/fred)
- [ ] `.mcpb` one-click Claude Desktop extension
- [ ] GeoFRED / maps (pairs with [census-mcp](https://github.com/mcpwright/census-mcp))

## Questions & feedback

[Discussions](https://github.com/mcpwright/fred-mcp/discussions) for questions
and ideas · [Issues](https://github.com/mcpwright/fred-mcp/issues) for bugs.

---

Part of **[mcpwright](https://mcpwright.com)** — polished MCP servers for
authoritative public data · built by [Devender Gollapally](https://devender.me).
FRED® and ALFRED® are registered trademarks of the Federal Reserve Bank of
St. Louis. This project is not affiliated with, endorsed, or certified by the
Federal Reserve Bank of St. Louis.
