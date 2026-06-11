"""compare_series + get_release_calendar tools."""

import httpx
import pytest
import respx

from fred_mcp import server
from fred_mcp.fred_client import BASE_URL

from .conftest import observations_payload, series_payload


def _series_route(series_id: str, frequency_short: str) -> None:
    respx.get(f"{BASE_URL}/series", params__contains={"series_id": series_id}).mock(
        return_value=httpx.Response(
            200,
            json=series_payload(
                series_id,
                frequency="Monthly" if frequency_short == "M" else "Quarterly",
                frequency_short=frequency_short,
            ),
        )
    )


@respx.mock
async def test_compare_series_aligns_rows(ctx):
    _series_route("UNRATE", "M")
    _series_route("JTSJOL", "M")
    respx.get(
        f"{BASE_URL}/series/observations", params__contains={"series_id": "UNRATE"}
    ).mock(
        return_value=httpx.Response(
            200,
            json=observations_payload([("2026-02-01", "4.0"), ("2026-01-01", "3.9")]),
        )
    )
    respx.get(
        f"{BASE_URL}/series/observations", params__contains={"series_id": "JTSJOL"}
    ).mock(
        return_value=httpx.Response(
            200, json=observations_payload([("2026-01-01", "8200")])
        )
    )
    result = await server.compare_series(["UNRATE", "JTSJOL"], ctx)
    assert [s.series_id for s in result.series] == ["UNRATE", "JTSJOL"]
    assert [r.date for r in result.rows] == ["2026-01-01", "2026-02-01"]
    assert result.rows[1].values == {"UNRATE": 4.0, "JTSJOL": None}


@respx.mock
async def test_compare_series_mixed_frequencies_require_explicit_frequency(ctx):
    _series_route("UNRATE", "M")
    _series_route("GDPC1", "Q")
    with pytest.raises(ValueError, match="different native frequencies"):
        await server.compare_series(["UNRATE", "GDPC1"], ctx)


@respx.mock
async def test_compare_series_mixed_frequencies_ok_when_harmonized(ctx):
    _series_route("UNRATE", "M")
    _series_route("GDPC1", "Q")
    obs_route = respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json=observations_payload([]))
    )
    await server.compare_series(["UNRATE", "GDPC1"], ctx, frequency="quarterly")
    for call in obs_route.calls:
        assert call.request.url.params["frequency"] == "q"


async def test_compare_series_requires_two_to_five(ctx):
    with pytest.raises(ValueError, match="2-5"):
        await server.compare_series(["UNRATE"], ctx)
    with pytest.raises(ValueError, match="2-5"):
        await server.compare_series(["A", "B", "C", "D", "E", "F"], ctx)


@respx.mock
async def test_release_calendar(ctx):
    route = respx.get(f"{BASE_URL}/releases/dates").mock(
        return_value=httpx.Response(
            200,
            json={
                "release_dates": [
                    {
                        "release_id": 50,
                        "release_name": "Employment Situation",
                        "date": "2026-06-12",
                    },
                    {
                        "release_id": 10,
                        "release_name": "Consumer Price Index",
                        "date": "2026-06-17",
                    },
                ]
            },
        )
    )
    cal = await server.get_release_calendar(ctx, days=10)
    params = route.calls.last.request.url.params
    assert params["include_release_dates_with_no_data"] == "true"
    assert [r.release_name for r in cal.releases] == [
        "Employment Situation",
        "Consumer Price Index",
    ]


async def test_release_calendar_bounds_days(ctx):
    with pytest.raises(ValueError, match="between 1 and 90"):
        await server.get_release_calendar(ctx, days=0)
    with pytest.raises(ValueError, match="between 1 and 90"):
        await server.get_release_calendar(ctx, days=365)
