"""search_series + get_series tools."""

import httpx
import pytest
import respx

from fred_mcp import server
from fred_mcp.fred_client import BASE_URL, FredError

from .conftest import series_payload


@respx.mock
async def test_search_series_returns_summaries(ctx):
    payload = {
        "seriess": [
            {
                "id": "UNRATE",
                "title": "Unemployment Rate",
                "units": "Percent",
                "frequency": "Monthly",
                "seasonal_adjustment_short": "SA",
                "last_updated": "2026-06-05",
                "popularity": 90,
                "notes": "The unemployment rate represents...",
            },
            {
                "id": "SPCS20RSA",
                "title": "S&P CoreLogic Case-Shiller 20-City",
                "units": "Index",
                "frequency": "Monthly",
                "seasonal_adjustment_short": "SA",
                "last_updated": "2026-05-27",
                "popularity": 70,
                "notes": "Copyright © 2026 S&P Dow Jones Indices LLC.",
            },
        ]
    }
    route = respx.get(f"{BASE_URL}/series/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    hits = await server.search_series("unemployment", ctx)
    assert [h.series_id for h in hits] == ["UNRATE", "SPCS20RSA"]
    assert hits[0].copyrighted is False
    assert hits[1].copyrighted is True  # third-party series flagged
    assert route.calls.last.request.url.params["order_by"] == "search_rank"


@respx.mock
async def test_search_series_clamps_limit(ctx):
    route = respx.get(f"{BASE_URL}/series/search").mock(
        return_value=httpx.Response(200, json={"seriess": []})
    )
    await server.search_series("gdp", ctx, limit=999)
    assert route.calls.last.request.url.params["limit"] == "50"


async def test_search_series_rejects_empty_query(ctx):
    with pytest.raises(ValueError, match="non-empty"):
        await server.search_series("   ", ctx)


@respx.mock
async def test_get_series_metadata_and_notes_passthrough(ctx):
    notes = "Copyright © 2026, Owner. Methodology details..."
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload(notes=notes))
    )
    info = await server.get_series("GDPC1", ctx)
    assert info.series_id == "GDPC1"
    assert info.notes == notes  # verbatim — notices never stripped
    assert info.copyrighted is True
    assert info.observation_start == "1947-01-01"


@respx.mock
async def test_get_series_uppercases_id(ctx):
    route = respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    await server.get_series("gdpc1", ctx)
    assert route.calls.last.request.url.params["series_id"] == "GDPC1"


@respx.mock
async def test_get_series_unknown_is_actionable(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json={"seriess": []})
    )
    with pytest.raises(FredError, match="search_series"):
        await server.get_series("NOPE", ctx)
