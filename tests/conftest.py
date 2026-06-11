"""Shared test fixtures."""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from fred_mcp.fred_client import FredClient


@pytest.fixture
async def fred() -> AsyncIterator[FredClient]:
    """A real client (keyed, unthrottled) whose HTTP respx intercepts."""
    client = FredClient(api_key="test-key")
    client._limiter = None  # don't pace mocked requests
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def ctx(fred: FredClient) -> SimpleNamespace:
    """A minimal stand-in for the MCP Context the server injects.

    Tools read the FRED client via ``ctx.request_context.lifespan_context.fred``;
    this provides exactly that.
    """
    return SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=SimpleNamespace(fred=fred))
    )


def series_payload(
    series_id: str = "GDPC1",
    *,
    title: str = "Real Gross Domestic Product",
    units: str = "Percent Change from Preceding Period",
    frequency: str = "Quarterly",
    frequency_short: str = "Q",
    notes: str | None = "Real gross domestic product...",
) -> dict:
    """A /series response with one series."""
    return {
        "seriess": [
            {
                "id": series_id,
                "title": title,
                "units": units,
                "frequency": frequency,
                "frequency_short": frequency_short,
                "seasonal_adjustment": "Seasonally Adjusted Annual Rate",
                "seasonal_adjustment_short": "SAAR",
                "observation_start": "1947-01-01",
                "observation_end": "2026-01-01",
                "last_updated": "2026-05-29 07:31:02-05",
                "popularity": 95,
                "notes": notes,
            }
        ]
    }


def observations_payload(
    rows: list[tuple[str, str]], *, count: int | None = None
) -> dict:
    """A /series/observations response from (date, value) pairs."""
    return {
        "count": count if count is not None else len(rows),
        "observations": [{"date": d, "value": v} for d, v in rows],
    }
