"""Async HTTP client for the FRED® API (api.stlouisfed.org).

This product uses the FRED® API but is not endorsed or certified by the Federal
Reserve Bank of St. Louis. Use requires a free personal API key
(``FRED_API_KEY``) and is subject to the FRED® API Terms of Use:
https://fred.stlouisfed.org/docs/api/terms_of_use.html

Terms-compliance notes baked into this client:
- A key is required and is the USER'S OWN (keys are personal under the terms);
  we fail fast before any network call when it's missing.
- We identify ourselves with a descriptive User-Agent (no cloaking).
- We throttle below FRED's ~120 requests/minute limit and cache responses, so
  the server is a polite API citizen (no bulk mirroring — live reads only).

The HTTP plumbing (retry/backoff, throttle, lifecycle) lives in
``mcpwright_core.AsyncHttpClient``; this module adds the FRED endpoints and a
two-tier response cache: vintage reads pinned to a past real-time period are
IMMUTABLE (what was known on a date never changes) and cache for ~30 days,
while current-period reads use short TTLs.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any, cast

import httpx
from mcpwright_core import AsyncHttpClient, RateLimiter, TTLCache
from mcpwright_core.errors import HttpError

BASE_URL = "https://api.stlouisfed.org/fred"
KEY_SIGNUP_URL = "https://fred.stlouisfed.org/docs/api/api_key_request.html"
TERMS_OF_USE_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"

# FRED treats this realtime_end as "current"; rows carrying it are still live.
CURRENT_REALTIME_END = "9999-12-31"
# The earliest realtime_start the API accepts — "the beginning of time".
EARLIEST_REALTIME_START = "1776-07-04"

DEFAULT_USER_AGENT = os.environ.get(
    "FRED_MCP_USER_AGENT",
    "fred-mcp/0.1 (https://github.com/mcpwright/fred-mcp)",
)

# FRED's documented limit is ~120 requests/minute; 1.5/s leaves headroom.
_RATE_PER_SEC = 1.5

# Cache TTLs (seconds), keyed on volatility. Vintage reads pinned to a past
# real-time period can never change — cache them for a long time.
_TTL_VINTAGE = 30 * 24 * 3600
_TTL_METADATA = 24 * 3600  # series metadata / search results
_TTL_DEFAULT = 3600  # current observations / release calendar


class FredError(HttpError):
    """Raised when the FRED API returns an error we can't recover from."""


class MissingKeyError(FredError):
    """Raised when no FRED API key is configured."""

    def __init__(self) -> None:
        super().__init__(
            "A FRED API key is required. Get a free one in seconds at "
            f"{KEY_SIGNUP_URL} and set the FRED_API_KEY environment variable. "
            f"(Keys are personal — see the terms of use: {TERMS_OF_USE_URL})"
        )


def _cache_key(path: str, params: dict[str, Any]) -> str:
    query = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{path}?{query}"


def _is_past(date_str: str, today: dt.date) -> bool:
    try:
        return dt.date.fromisoformat(date_str) < today
    except ValueError:
        return False


def _ttl_for(path: str, params: dict[str, Any], today: dt.date) -> float:
    """How long a response may be cached.

    A read whose real-time window ends in the past is a vintage snapshot —
    immutable by construction — so it gets the long TTL. Metadata and search
    change rarely; everything else (current observations, the release
    calendar) stays fresh-ish.
    """
    realtime_end = str(params.get("realtime_end", ""))
    if (
        realtime_end
        and realtime_end != CURRENT_REALTIME_END
        and _is_past(realtime_end, today)
    ):
        return _TTL_VINTAGE
    if path in ("/series", "/series/search"):
        return _TTL_METADATA
    return _TTL_DEFAULT


class FredClient(AsyncHttpClient):
    """FRED API client: the shared HTTP base + a volatility-aware cache.

    Throttled under FRED's rate limit, retrying transient errors, requiring
    the user's own free API key (fail-fast when missing), and caching with
    long TTLs for immutable vintage reads.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = 3,
        cache: bool = True,
    ) -> None:
        super().__init__(
            user_agent=user_agent,
            max_retries=max_retries,
            rate_limiter=RateLimiter.per_second(_RATE_PER_SEC),
            error_cls=FredError,
            follow_redirects=True,
        )
        self._key = api_key or os.environ.get("FRED_API_KEY") or None
        # On by default; set FRED_MCP_CACHE=0 to disable.
        enabled = cache and os.environ.get("FRED_MCP_CACHE", "1") not in ("0", "false")
        self._cache: TTLCache | None = TTLCache() if enabled else None

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    async def fred_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET a FRED endpoint and parse the JSON body (cached by volatility).

        ``path`` is relative to the API base (e.g. ``/series/observations``).
        The API key and ``file_type=json`` are added here; the key is NOT part
        of the cache key. FRED's 4xx error bodies carry a useful
        ``error_message`` — surface it instead of a bare status code.
        """
        if not self._key:
            raise MissingKeyError()
        key = f"json:{_cache_key(path, params)}"
        if self._cache is not None:
            hit, value = await self._cache.get(key)
            if hit:
                return cast("dict[str, Any]", value)
        full = dict(params)
        full["api_key"] = self._key
        full["file_type"] = "json"
        try:
            resp = await self.request("GET", BASE_URL + path, params=full)
        except httpx.HTTPStatusError as exc:
            raise FredError(_fred_error_message(exc.response)) from exc
        data: dict[str, Any] = resp.json()
        if self._cache is not None:
            ttl = _ttl_for(path, params, dt.date.today())
            await self._cache.set(key, data, ttl, size=len(resp.content))
        return data

    # --- typed endpoint helpers --------------------------------------------
    async def series(
        self, series_id: str, *, realtime: str | None = None
    ) -> dict[str, Any]:
        """Metadata for one series (optionally as known on ``realtime``)."""
        params: dict[str, Any] = {"series_id": series_id}
        if realtime:
            params["realtime_start"] = realtime
            params["realtime_end"] = realtime
        return await self.fred_json("/series", params)

    async def series_search(self, text: str, *, limit: int = 10) -> dict[str, Any]:
        """Full-text search over series, best matches first."""
        return await self.fred_json(
            "/series/search",
            {"search_text": text, "limit": limit, "order_by": "search_rank"},
        )

    async def observations(self, series_id: str, **params: Any) -> dict[str, Any]:
        """Observations for a series; pass FRED query params through."""
        return await self.fred_json(
            "/series/observations", {"series_id": series_id, **params}
        )

    async def vintage_dates(
        self, series_id: str, *, limit: int = 10000, sort_order: str = "asc"
    ) -> dict[str, Any]:
        """The dates on which a series' data was released or revised."""
        return await self.fred_json(
            "/series/vintagedates",
            {"series_id": series_id, "limit": limit, "sort_order": sort_order},
        )

    async def series_release(self, series_id: str) -> dict[str, Any]:
        """The release a series belongs to."""
        return await self.fred_json("/series/release", {"series_id": series_id})

    async def release_dates(
        self, release_id: int, *, start: str, end: str, limit: int = 30
    ) -> dict[str, Any]:
        """Scheduled/actual dates for one release within a window."""
        return await self.fred_json(
            "/release/dates",
            {
                "release_id": release_id,
                "realtime_start": start,
                "realtime_end": end,
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
                "limit": limit,
            },
        )

    async def releases_dates(
        self, *, start: str, end: str, limit: int = 200
    ) -> dict[str, Any]:
        """Release dates across ALL releases within a window (the calendar)."""
        return await self.fred_json(
            "/releases/dates",
            {
                "realtime_start": start,
                "realtime_end": end,
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
                "limit": limit,
            },
        )


def _fred_error_message(resp: httpx.Response) -> str:
    """The API's own error_message when present, else a generic line."""
    try:
        body = resp.json()
        message = body.get("error_message")
        if message:
            return f"FRED API error {resp.status_code}: {message}"
    except ValueError:
        pass
    return f"FRED API error {resp.status_code} for {resp.url}"
