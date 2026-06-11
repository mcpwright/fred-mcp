"""get_observations + get_latest tools."""

import httpx
import pytest
import respx

from fred_mcp import server
from fred_mcp.fred_client import BASE_URL

from .conftest import observations_payload, series_payload


@respx.mock
async def test_get_observations_chronological_and_truncation(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    # The client fetches newest-first (to keep the recent end under the cap)...
    rows = [
        ("2026-01-01", "1.4"),
        ("2025-10-01", "2.1"),
        ("2025-07-01", "."),
    ]
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json=observations_payload(rows, count=300))
    )
    result = await server.get_observations("GDPC1", ctx, max_points=3)
    # ...and the tool returns them oldest-first, with '.' as null.
    assert [o.date for o in result.observations] == [
        "2025-07-01",
        "2025-10-01",
        "2026-01-01",
    ]
    assert result.observations[0].value is None
    assert result.truncated is True  # 300 exist, 3 returned


@respx.mock
async def test_get_observations_transform_mapping(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    route = respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json=observations_payload([]))
    )
    result = await server.get_observations("GDPC1", ctx, transform="pct_change_yoy")
    params = route.calls.last.request.url.params
    assert params["units"] == "pc1"  # the FRED code, hidden from the model
    assert result.units == "% change from year ago"
    assert result.transform == "pct_change_yoy"


@respx.mock
async def test_get_observations_level_keeps_native_units(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload(units="Percent"))
    )
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json=observations_payload([]))
    )
    result = await server.get_observations("UNRATE", ctx)
    assert result.units == "Percent"


@respx.mock
async def test_get_observations_frequency_downsample_params(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    route = respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json=observations_payload([]))
    )
    await server.get_observations("GDPC1", ctx, frequency="annual", aggregation="eop")
    params = route.calls.last.request.url.params
    assert params["frequency"] == "a"
    assert params["aggregation_method"] == "eop"


async def test_get_observations_rejects_bad_inputs(ctx):
    with pytest.raises(ValueError, match="transform"):
        await server.get_observations("GDPC1", ctx, transform="zscore")
    with pytest.raises(ValueError, match="frequency"):
        await server.get_observations("GDPC1", ctx, frequency="hourly")
    with pytest.raises(ValueError, match="ISO date"):
        await server.get_observations("GDPC1", ctx, start="last year")
    with pytest.raises(ValueError, match="max_points"):
        await server.get_observations("GDPC1", ctx, max_points=0)


@respx.mock
async def test_get_latest_with_next_release(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload(units="Percent"))
    )
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(
            200, json=observations_payload([("2026-05-01", "3.9")], count=900)
        )
    )
    respx.get(f"{BASE_URL}/series/release").mock(
        return_value=httpx.Response(
            200, json={"releases": [{"id": 50, "name": "Employment Situation"}]}
        )
    )
    respx.get(f"{BASE_URL}/release/dates").mock(
        return_value=httpx.Response(
            200, json={"release_dates": [{"release_id": 50, "date": "2026-07-02"}]}
        )
    )
    latest = await server.get_latest("UNRATE", ctx)
    assert latest.value == 3.9
    assert latest.date == "2026-05-01"
    assert latest.next_release_date == "2026-07-02"


@respx.mock
async def test_get_latest_without_schedule(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(
            200, json=observations_payload([("2026-05-01", "3.9")])
        )
    )
    respx.get(f"{BASE_URL}/series/release").mock(
        return_value=httpx.Response(200, json={"releases": []})
    )
    latest = await server.get_latest("UNRATE", ctx)
    assert latest.next_release_date is None


@respx.mock
async def test_get_latest_skips_missing_holiday_rows(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload(units="Percent"))
    )
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(
            200,
            json=observations_payload(
                [("2026-06-09", "."), ("2026-06-08", "4.41"), ("2026-06-07", "4.39")]
            ),
        )
    )
    respx.get(f"{BASE_URL}/series/release").mock(
        return_value=httpx.Response(200, json={"releases": []})
    )
    latest = await server.get_latest("DGS10", ctx)
    assert latest.value == 4.41  # the '.' holiday row is skipped
    assert latest.date == "2026-06-08"
