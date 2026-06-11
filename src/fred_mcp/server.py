"""fred-mcp — MCP server for FRED® economic data, with ALFRED® vintage tools.

This product uses the FRED® API but is not endorsed or certified by the
Federal Reserve Bank of St. Louis.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcpwright_core import READ_ONLY, app_context

from .formatting import (
    align_comparison_rows,
    build_revision_steps,
    to_observations,
    to_series_info,
    to_series_summary,
    total_revision,
)
from .fred_client import (
    CURRENT_REALTIME_END,
    EARLIEST_REALTIME_START,
    TERMS_OF_USE_URL,
    FredClient,
    FredError,
)
from .models import (
    AsOfResult,
    ComparisonResult,
    ComparisonSeries,
    LatestValue,
    ObservationsResult,
    ReleaseCalendar,
    ReleaseDateEntry,
    RevisionHistory,
    SeriesInfo,
    SeriesSummary,
    VintageDatesResult,
)

# Curated transforms -> FRED `units` codes. Friendly names only; the model
# should never need to know FRED's internal codes.
_TRANSFORMS: dict[str, tuple[str, str]] = {
    "level": ("lin", ""),  # units label = the series' native units
    "change": ("chg", "change from previous period"),
    "pct_change": ("pch", "% change from previous period"),
    "pct_change_yoy": ("pc1", "% change from year ago"),
    "log": ("log", "natural log"),
}

# Friendly frequency names -> FRED frequency codes (downsampling only).
_FREQUENCIES: dict[str, str] = {
    "daily": "d",
    "weekly": "w",
    "monthly": "m",
    "quarterly": "q",
    "semiannual": "sa",
    "annual": "a",
}

_AGGREGATIONS = ("avg", "sum", "eop")

_MAX_POINTS_CAP = 1000
_MAX_VINTAGES_LISTED = 60
_MAX_REVISION_STEPS = 60

_INSTRUCTIONS = f"""\
Read-only access to FRED® — 800,000+ U.S. and international economic time
series from the Federal Reserve Bank of St. Louis — including ALFRED® vintage
data: what every number said AS ORIGINALLY PUBLISHED, before revisions.

Typical flow:
- `search_series` finds series IDs ("unemployment rate" -> UNRATE); `get_series`
  returns one series' full metadata and notes.
- `get_observations` is the workhorse: a date window of values with optional
  transform (pct_change_yoy, etc.) and downsampling. `get_latest` answers
  "what is X right now" with the next scheduled release date.
- `compare_series` aligns 2-5 series on one date axis.
- `get_release_calendar` lists upcoming data releases ("when's the next jobs
  report?").
- Vintage lane (the distinctive part): `get_series_as_of` shows a series
  exactly as known on a past date; `get_revision_history` walks one data
  point's life from initial print through every revision to today;
  `get_vintage_dates` shows when a series was released/revised.

Notes:
- REVISIONS MATTER: current values often differ from what was originally
  published. For "what did policymakers see at the time", use the vintage
  tools, not current data.
- Some series are third-party-copyrighted (the `copyrighted` flag; their
  `notes` carry the owner's terms — required reading before non-personal use).
- Values use the series' units — always check the `units` field; transforms
  change the meaning of the numbers.
- Requires the user's own free FRED API key in FRED_API_KEY (get one at
  fred.stlouisfed.org/docs/api/api_key_request.html).

This product uses the FRED® API but is not endorsed or certified by the
Federal Reserve Bank of St. Louis. Use is subject to the FRED API Terms of
Use: {TERMS_OF_USE_URL}
"""


@dataclass
class AppContext:
    """Resources shared across requests for the lifetime of the server."""

    fred: FredClient


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Own the FRED HTTP client: create on startup, close on shutdown."""
    fred = FredClient()
    try:
        yield AppContext(fred=fred)
    finally:
        await fred.aclose()


mcp = FastMCP("fred", instructions=_INSTRUCTIONS, lifespan=_lifespan)


def _fred(ctx: Context) -> FredClient:
    """The shared FRED client from the lifespan context."""
    return app_context(ctx, AppContext).fred


def _validate_date(value: str, name: str) -> str:
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD), got {value!r}")


def _transform_code(transform: str) -> str:
    if transform not in _TRANSFORMS:
        raise ValueError(
            f"Unknown transform {transform!r}. One of: {', '.join(_TRANSFORMS)}."
        )
    return _TRANSFORMS[transform][0]


def _units_label(transform: str, native_units: str) -> str:
    label = _TRANSFORMS[transform][1]
    return label or native_units


def _clamp_points(max_points: int) -> int:
    if max_points < 1:
        raise ValueError("max_points must be >= 1")
    return min(max_points, _MAX_POINTS_CAP)


def _window_params(
    *,
    start: str | None,
    end: str | None,
    max_points: int,
    transform: str = "level",
    frequency: str | None = None,
    aggregation: str = "avg",
    realtime: str | None = None,
) -> dict[str, Any]:
    """Validate tool inputs and build observation query params.

    Pure validation — called BEFORE any network I/O so bad inputs fail fast
    without spending an API call.
    """
    params: dict[str, Any] = {
        "sort_order": "desc",
        "limit": _clamp_points(max_points),
        "units": _transform_code(transform),
    }
    if start:
        params["observation_start"] = _validate_date(start, "start")
    if end:
        params["observation_end"] = _validate_date(end, "end")
    if frequency is not None:
        if frequency not in _FREQUENCIES:
            raise ValueError(
                f"Unknown frequency {frequency!r}. One of: {', '.join(_FREQUENCIES)}."
            )
        if aggregation not in _AGGREGATIONS:
            raise ValueError(
                f"Unknown aggregation {aggregation!r}. One of: {', '.join(_AGGREGATIONS)}."
            )
        params["frequency"] = _FREQUENCIES[frequency]
        params["aggregation_method"] = aggregation
    if realtime is not None:
        params["realtime_start"] = realtime
        params["realtime_end"] = realtime
    return params


async def _fetch_window(
    fred: FredClient, series_id: str, params: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool]:
    """The newest ``limit`` observations in a window, chronological.

    Fetched newest-first so the cap keeps the RECENT end of the window, then
    reversed. Returns (rows, truncated).
    """
    data = await fred.observations(series_id, **params)
    rows = list(reversed(data.get("observations", [])))
    truncated = int(data.get("count", len(rows))) > len(rows)
    return rows, truncated


@mcp.tool(title="Search for series", annotations=READ_ONLY)
async def search_series(
    query: str, ctx: Context, limit: int = 10
) -> list[SeriesSummary]:
    """Find FRED series by free-text search, best matches first.

    `query`: plain words (e.g. "unemployment rate", "median home price").
    Returns series IDs with title, units, native frequency, and a
    `copyrighted` flag — some FRED series are owned by third parties whose
    terms (in the series notes) apply beyond personal use. Resolve a series
    ID here first; the data tools key off it.
    """
    if not query.strip():
        raise ValueError("query must be non-empty")
    data = await _fred(ctx).series_search(query, limit=max(1, min(limit, 50)))
    return [to_series_summary(s) for s in data.get("seriess", [])]


@mcp.tool(title="Get series metadata", annotations=READ_ONLY)
async def get_series(series_id: str, ctx: Context) -> SeriesInfo:
    """Full metadata for one series: units, frequency, range, and notes.

    `series_id`: a FRED series ID (e.g. "GDPC1"). The `notes` are returned
    verbatim — they carry methodology caveats and, for third-party series,
    the owner's copyright terms (also flagged via `copyrighted`).
    """
    data = await _fred(ctx).series(series_id.strip().upper())
    seriess = data.get("seriess", [])
    if not seriess:
        raise FredError(f"Series {series_id!r} not found — try search_series.")
    return to_series_info(seriess[0])


@mcp.tool(title="Get observations", annotations=READ_ONLY)
async def get_observations(
    series_id: str,
    ctx: Context,
    start: str | None = None,
    end: str | None = None,
    transform: str = "level",
    frequency: str | None = None,
    aggregation: str = "avg",
    max_points: int = 120,
) -> ObservationsResult:
    """A series' values in a date window, optionally transformed/downsampled.

    `series_id`: a FRED series ID. `start`/`end`: ISO dates bounding the
    window. `transform`: level | change | pct_change | pct_change_yoy | log.
    `frequency`: optionally downsample to daily/weekly/monthly/quarterly/
    semiannual/annual (with `aggregation` avg | sum | eop); only coarser than
    the native frequency is valid. `max_points` caps the result, keeping the
    most RECENT points (`truncated` tells you when the cap bit).

    Values are CURRENT (post-revision) data. For numbers as originally
    published, use `get_series_as_of` / `get_revision_history`.
    """
    params = _window_params(
        start=start,
        end=end,
        max_points=max_points,
        transform=transform,
        frequency=frequency,
        aggregation=aggregation,
    )
    fred = _fred(ctx)
    sid = series_id.strip().upper()
    meta = await fred.series(sid)
    seriess = meta.get("seriess", [])
    if not seriess:
        raise FredError(f"Series {series_id!r} not found — try search_series.")
    info = seriess[0]
    rows, truncated = await _fetch_window(fred, sid, params)
    return ObservationsResult(
        series_id=sid,
        title=info.get("title", ""),
        units=_units_label(transform, info.get("units", "")),
        transform=transform,
        frequency=(frequency or info.get("frequency", "")),
        observations=to_observations(rows),
        truncated=truncated,
    )


@mcp.tool(title="Get latest value", annotations=READ_ONLY)
async def get_latest(series_id: str, ctx: Context) -> LatestValue:
    """The most recent value of a series, plus its next scheduled release.

    `series_id`: a FRED series ID. The value is the most recent NON-MISSING
    print (daily series publish '.' on holidays) and is CURRENT data — it may
    itself be revised later (see `get_revision_history` for how much this
    series typically moves). `next_release_date` is null when FRED publishes
    no schedule for the series' release.
    """
    fred = _fred(ctx)
    sid = series_id.strip().upper()
    meta = await fred.series(sid)
    seriess = meta.get("seriess", [])
    if not seriess:
        raise FredError(f"Series {series_id!r} not found — try search_series.")
    info = seriess[0]
    # Daily series publish '.' (missing) rows on holidays/weekends — look a
    # few rows back for the most recent real value.
    data = await fred.observations(sid, sort_order="desc", limit=7)
    observations = to_observations(data.get("observations", []))
    if not observations:
        raise FredError(f"Series {sid} has no observations.")
    latest = next((o for o in observations if o.value is not None), observations[0])
    return LatestValue(
        series_id=sid,
        title=info.get("title", ""),
        date=latest.date,
        value=latest.value,
        units=info.get("units", ""),
        last_updated=info.get("last_updated", ""),
        next_release_date=await _next_release_date(fred, sid),
    )


async def _next_release_date(fred: FredClient, series_id: str) -> str | None:
    """The series' next scheduled release date, if FRED publishes one."""
    today = dt.date.today()
    try:
        release = await fred.series_release(series_id)
        releases = release.get("releases", [])
        if not releases:
            return None
        data = await fred.release_dates(
            int(releases[0]["id"]),
            start=today.isoformat(),
            end=(today + dt.timedelta(days=400)).isoformat(),
        )
        for entry in data.get("release_dates", []):
            if entry.get("date", "") >= today.isoformat():
                return str(entry["date"])
    except FredError:
        return None
    return None


@mcp.tool(title="Compare series", annotations=READ_ONLY)
async def compare_series(
    series_ids: list[str],
    ctx: Context,
    start: str | None = None,
    end: str | None = None,
    transform: str = "level",
    frequency: str | None = None,
    max_points: int = 120,
) -> ComparisonResult:
    """Align 2-5 series on one date axis for comparison.

    `series_ids`: 2-5 FRED series IDs. Same `start`/`end`/`transform` as
    `get_observations`. If the series have DIFFERENT native frequencies you
    must pass `frequency` (a frequency at least as coarse as the coarsest
    series) — mixing frequencies without it returns misaligned dates. Units
    differ per series unless a relative transform (e.g. pct_change_yoy) is
    used — check each entry's `units` before comparing levels.
    """
    ids = [s.strip().upper() for s in series_ids if s.strip()]
    if not 2 <= len(ids) <= 5:
        raise ValueError("Pass 2-5 series IDs to compare.")
    params = _window_params(
        start=start,
        end=end,
        max_points=max_points,
        transform=transform,
        frequency=frequency,
    )
    fred = _fred(ctx)
    metas = await asyncio.gather(*(fred.series(sid) for sid in ids))
    infos: list[dict[str, Any]] = []
    for sid, meta in zip(ids, metas, strict=True):
        seriess = meta.get("seriess", [])
        if not seriess:
            raise FredError(f"Series {sid!r} not found — try search_series.")
        infos.append(seriess[0])
    native = {i.get("frequency_short", i.get("frequency", "")) for i in infos}
    if len(native) > 1 and frequency is None:
        raise ValueError(
            "These series have different native frequencies "
            f"({', '.join(sorted(native))}) — pass `frequency` (at least as "
            "coarse as the coarsest series) to align them."
        )
    windows = await asyncio.gather(*(_fetch_window(fred, sid, params) for sid in ids))
    per_series = {
        sid: to_observations(rows) for sid, (rows, _t) in zip(ids, windows, strict=True)
    }
    return ComparisonResult(
        series=[
            ComparisonSeries(
                series_id=sid,
                title=info.get("title", ""),
                units=_units_label(transform, info.get("units", "")),
                frequency=info.get("frequency", ""),
            )
            for sid, info in zip(ids, infos, strict=True)
        ],
        transform=transform,
        rows=align_comparison_rows(per_series),
        truncated=any(t for _rows, t in windows),
    )


@mcp.tool(title="Get release calendar", annotations=READ_ONLY)
async def get_release_calendar(ctx: Context, days: int = 14) -> ReleaseCalendar:
    """Upcoming data-release dates ("when is the next jobs report / CPI?").

    `days`: how far ahead to look (1-90, default 14). Returns each release's
    name and date, soonest first. Dates are the SCHEDULED dates FRED knows
    about; not every release publishes a schedule.
    """
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    today = dt.date.today()
    end = today + dt.timedelta(days=days)
    data = await _fred(ctx).releases_dates(start=today.isoformat(), end=end.isoformat())
    rows = data.get("release_dates", [])
    return ReleaseCalendar(
        start=today.isoformat(),
        end=end.isoformat(),
        releases=[
            ReleaseDateEntry(
                release_id=int(r["release_id"]),
                release_name=str(r.get("release_name", "")),
                date=str(r["date"]),
            )
            for r in rows
        ],
        truncated=int(data.get("count", len(rows))) > len(rows),
    )


@mcp.tool(title="Get series as of a date (vintage)", annotations=READ_ONLY)
async def get_series_as_of(
    series_id: str,
    as_of: str,
    ctx: Context,
    start: str | None = None,
    end: str | None = None,
    max_points: int = 120,
) -> AsOfResult:
    """A series EXACTLY as it was known on a past date — before later revisions.

    `series_id`: a FRED series ID. `as_of`: the knowledge date (ISO) — e.g.
    "2009-03-18" shows the data the Fed saw at its March 2009 meeting.
    `start`/`end` bound the observation window as usual.

    Vintage coverage varies by series: dates before the first vintage have no
    data (check `get_vintage_dates`). Values can differ sharply from today's —
    that's the point.
    """
    sid = series_id.strip().upper()
    as_of_date = _validate_date(as_of, "as_of")
    if as_of_date > dt.date.today().isoformat():
        raise ValueError("as_of must not be in the future")
    params = _window_params(
        start=start, end=end, max_points=max_points, realtime=as_of_date
    )
    fred = _fred(ctx)
    # Metadata as known on as_of too — units/title can change across vintages
    # (e.g. GDP re-basings); fall back to current metadata if the vintage
    # metadata isn't available.
    try:
        meta = await fred.series(sid, realtime=as_of_date)
    except FredError:
        meta = await fred.series(sid)
    seriess = meta.get("seriess", [])
    if not seriess:
        raise FredError(f"Series {series_id!r} not found — try search_series.")
    info = seriess[0]
    try:
        rows, truncated = await _fetch_window(fred, sid, params)
    except FredError as exc:
        message = str(exc)
        if "400" in message or "vintage" in message.lower():
            message += (
                " — if as_of predates the series' first vintage there is no "
                "data for that date; check get_vintage_dates."
            )
        raise FredError(message)
    return AsOfResult(
        series_id=sid,
        title=info.get("title", ""),
        as_of=as_of_date,
        units=info.get("units", ""),
        observations=to_observations(rows),
        truncated=truncated,
    )


@mcp.tool(title="Get a data point's revision history", annotations=READ_ONLY)
async def get_revision_history(
    series_id: str, observation_date: str, ctx: Context
) -> RevisionHistory:
    """One data point's life across revisions: earliest archived print -> today.

    `series_id`: a FRED series ID. `observation_date`: the data point's PERIOD
    START date (ISO) — quarterly series use quarter starts (Q4 2008 =
    "2008-10-01"), monthly use month starts. Returns the earliest archived
    value, every revision with its publication date, the current value, and
    the total drift.

    Caveat: ALFRED's archive starts late for many series (`archive_starts`
    shows where). `initial_value` is the true first print — what
    decision-makers actually saw — only when the archive reaches back to the
    observation's original release.
    """
    fred = _fred(ctx)
    sid = series_id.strip().upper()
    obs_date = _validate_date(observation_date, "observation_date")
    meta = await fred.series(sid)
    seriess = meta.get("seriess", [])
    if not seriess:
        raise FredError(f"Series {series_id!r} not found — try search_series.")
    info = seriess[0]
    data = await fred.observations(
        sid,
        observation_start=obs_date,
        observation_end=obs_date,
        realtime_start=EARLIEST_REALTIME_START,
        realtime_end=CURRENT_REALTIME_END,
        output_type=1,
    )
    rows = data.get("observations", [])
    if not rows:
        raise FredError(
            f"No observation of {sid} dated {obs_date}. Use the period START "
            "date (e.g. 2008-10-01 for Q4 2008 in a quarterly series); "
            "get_series shows the series' frequency and range."
        )
    steps = build_revision_steps(rows)
    steps_truncated = len(steps) > _MAX_REVISION_STEPS
    if steps_truncated:
        steps = steps[: _MAX_REVISION_STEPS - 1] + steps[-1:]
    return RevisionHistory(
        series_id=sid,
        title=info.get("title", ""),
        observation_date=obs_date,
        units=info.get("units", ""),
        archive_starts=steps[0].published_on if steps else None,
        initial_value=steps[0].value if steps else None,
        current_value=steps[-1].value if steps and steps[-1].is_current else None,
        total_revision=total_revision(steps),
        steps=steps,
        steps_truncated=steps_truncated,
    )


@mcp.tool(title="Get vintage dates", annotations=READ_ONLY)
async def get_vintage_dates(series_id: str, ctx: Context) -> VintageDatesResult:
    """When a series' data was released or revised (its ALFRED vintages).

    `series_id`: a FRED series ID. Answers "how often is this revised?" and
    bounds the vintage tools: `get_series_as_of` has no data before
    `first_vintage`. The full list is capped to the most recent dates;
    `total_vintages` is the true count.
    """
    fred = _fred(ctx)
    sid = series_id.strip().upper()
    data = await fred.vintage_dates(sid)
    dates: list[str] = list(data.get("vintage_dates", []))
    if not dates:
        raise FredError(
            f"No vintage dates for {series_id!r} — check the series ID "
            "(try search_series)."
        )
    total = int(data.get("count", len(dates)))
    if total > len(dates):
        # >10k vintages — the asc fetch missed the newest; fetch those desc.
        desc = await fred.vintage_dates(
            sid, limit=_MAX_VINTAGES_LISTED, sort_order="desc"
        )
        newest_first = list(desc.get("vintage_dates", []))
    else:
        newest_first = list(reversed(dates))
    return VintageDatesResult(
        series_id=sid,
        total_vintages=total,
        first_vintage=dates[0],
        latest_vintage=newest_first[0] if newest_first else dates[-1],
        vintage_dates=newest_first[:_MAX_VINTAGES_LISTED],
        truncated=total > _MAX_VINTAGES_LISTED,
    )


def _quiet_http_logging() -> None:
    """Keep httpx/httpcore request logs out of client-visible output.

    httpx logs every request URL at INFO — and FRED's URL carries the user's
    api_key as a query param. Capping these loggers at WARNING means the key
    cannot reach a host that captures the server's stderr, regardless of the
    ambient logging configuration.
    """
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def main() -> None:
    """Run the MCP server on stdio."""
    _quiet_http_logging()
    mcp.run()
