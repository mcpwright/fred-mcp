# fred-mcp — working agreement

`fred-mcp` is server #4 of the **mcpwright** suite (`github.com/mcpwright`): polished,
public MCP servers that bring a real-world data source into any agent. It follows the
bar set by `edgar-mcp` (the reference server) and builds on `mcpwright-core`.

> The full written rubric is
> `~/my-notes/professional-self-improvement/mcpwright/mcp-standards.md`.
> The design doc is `~/my-notes/professional-self-improvement/mcpwright/fred-mcp-plan.md`.

## Non-negotiable policies

- **FRED ToU compliance** (this repo's special constraint — full review in the design doc):
  - **No bulk mirroring.** Live API + TTL cache only; never persist FRED data to disk.
  - **BYO key.** The user's own free `FRED_API_KEY`; never ship or embed a key; fail fast
    pre-network (`MissingKeyError`). The key is a **query param** — it must never appear
    in error messages, logs, or anything the model sees.
  - The disclaimer ("This product uses the FRED® API but is not endorsed or certified by
    the Federal Reserve Bank of St. Louis.") stays in the server `instructions`, README,
    and (at publish time) the MCPB manifest.
  - **Copyright pass-through.** Third-party series notes are returned verbatim, never
    stripped; the `copyrighted` flag stays accurate.
- **Lots of unit tests.** Every tool and every formatter has tests, with **all external
  I/O mocked** (`respx`). A new tool ships with its tests **in the same PR**.
- **Use the latest patterns.** Official `mcp` Python SDK via `mcp.server.fastmcp` (NOT the
  standalone `fastmcp` package). Python 3.12+ idioms, `from __future__ import annotations`,
  pydantic v2 models with a `Field(description=...)` on **every** field, `uv`, async
  `httpx` via `mcpwright_core.AsyncHttpClient`. Tools return typed pydantic models and are
  annotated `readOnlyHint=True`.
- **Honest tool surfaces.** Descriptions carry the caveats that change interpretation
  (revisions exist; vintage coverage varies; '.' means missing; truncation is flagged,
  never silent). Measured rationale: devender.me/2026/06/10/tool-descriptions-measured/.
- **PR per change, CI-gated.** Standard flow:
  **feature branch → code → code-review subagent → fold in findings → PR → CI green → squash-merge.**
  - *Code-review subagent:* before opening the PR, review the diff with the
    **`code-reviewer`** subagent (`.claude/agents/code-reviewer.md`) — or run
    **`/review-pr`**. Address Blocker/High (with a regression test for any real bug)
    before the PR opens.
  - *Merge:* `Code Quality & Tests` green and branch up to date → squash-merge with a
    `(#N)` suffix. `main` is branch-protected; **no direct pushes**.
- **Green locally before pushing:**
  ```bash
  uv run ruff check src/ && uv run ruff format --check src/ && uv run mypy && uv run pytest -v
  ```

## Layout

```
src/fred_mcp/
  fred_client.py   FredClient (mcpwright_core.AsyncHttpClient subclass) + the
                   volatility-aware TTL policy (vintage reads ~30d, metadata 24h, live 1h)
  models.py        pydantic return models (= the tool output schemas)
  formatting.py    pure raw-JSON -> model helpers (incl. the revision-step walk)
  server.py        FastMCP server: 9 read-only tools (6 everyday + 3 vintage lane)
tests/             respx-mocked; conftest has the ctx fixture + payload builders
```
