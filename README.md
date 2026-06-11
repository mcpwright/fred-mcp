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

**Status:** v0.1.0 — live on [PyPI](https://pypi.org/project/mcpwright-fred/)
(`uvx mcpwright-fred`) and the official MCP Registry
(`io.github.mcpwright/fred-mcp`). 9 tools, CI-gated, built on
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

## What can you ask?

Every question below was run live against the real FRED API through these
tools (answers as of June 2026 — ask again and they'll be current).

**Everyday questions:**

1. *"What's the unemployment rate right now, and when's the next jobs
   report?"* — `get_latest(UNRATE)` → 4.3% (May 2026), next release 2026-07-02.
2. *"What's the 10-year Treasury yield today?"* — `get_latest(DGS10)` → 4.53%
   (it correctly skips the `.` rows daily series publish on holidays).
3. *"How has inflation trended over the past year?"* —
   `get_observations(CPIAUCSL, transform=pct_change_yoy)` → 2.4% → 3.3% →
   3.8% → 4.2% over Feb–May 2026.
4. *"Find me data on median household income."* — `search_series` →
   `MEHOINUSA672N` (real) and `MEHOINUSA646N` (nominal), annual.
5. *"Is the labor market loosening? Compare unemployment and job openings
   since 2024."* — `compare_series([UNRATE, JTSJOL])` → one aligned table.
6. *"What economic data comes out this week?"* — `get_release_calendar(7)` →
   241 release dates, CPI included.
7. *"What was real GDP growth each quarter of 2025?"* —
   `get_observations(A191RL1Q225SBEA)` → −0.6, +3.8, +4.4, +0.5%.
8. *"Give me CPI as annual averages for the 2020s."* —
   `get_observations(CPIAUCSL, frequency=annual)` → one row per year.

**Questions only the vintage tools can answer:**

9. *"How bad did Q4-2008 GDP look to policymakers in early 2009, versus what
   we know now?"* — `get_series_as_of(GDPC1, "2009-02-15")` → a −3.8%
   annualized decline as known then (in chained-2000 dollars — the metadata
   is vintage-pinned too) versus −8.5% in today's data. Policy ran on the
   first number.
10. *"Was the May 2020 COVID unemployment rate ever revised?"* —
    `get_revision_history(UNRATE, "2020-05-01")` → first published as 13.3
    (2020-06-05), currently 13.2, with each revision dated.
11. *"What mortgage rate did the Fed see going into the March 2022 liftoff
    meeting?"* — `get_series_as_of(MORTGAGE30US, "2022-03-16")` → 3.85% as
    known then; 6.48% today.
12. *"How often does GDP actually get revised?"* — `get_vintage_dates(GDPC1)`
    → 415 vintages since 1991-12-04.

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
- [x] Publish to PyPI (`mcpwright-fred`) + the MCP Registry
- [x] Site page at [mcpwright.com/fred](https://mcpwright.com/fred)
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
