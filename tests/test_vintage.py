"""The vintage lane: get_series_as_of, get_revision_history, get_vintage_dates."""

import httpx
import pytest
import respx

from fred_mcp import server
from fred_mcp.fred_client import BASE_URL, FredError

from .conftest import observations_payload, series_payload


@respx.mock
async def test_get_series_as_of_pins_the_realtime_window(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    route = respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(
            200,
            json=observations_payload([("2008-10-01", "-3.8"), ("2008-07-01", "-0.5")]),
        )
    )
    result = await server.get_series_as_of("GDPC1", "2009-02-15", ctx)
    params = route.calls.last.request.url.params
    assert params["realtime_start"] == "2009-02-15"
    assert params["realtime_end"] == "2009-02-15"
    assert result.as_of == "2009-02-15"
    # chronological, and showing the as-published value
    assert [o.date for o in result.observations] == ["2008-07-01", "2008-10-01"]
    assert result.observations[-1].value == -3.8


async def test_get_series_as_of_rejects_future_dates(ctx):
    with pytest.raises(ValueError, match="future"):
        await server.get_series_as_of("GDPC1", "2999-01-01", ctx)


@respx.mock
async def test_get_series_as_of_predating_vintages_is_actionable(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(
            400,
            json={
                "error_code": 400,
                "error_message": "this exceeds the earliest vintage",
            },
        )
    )
    with pytest.raises(FredError, match="get_vintage_dates"):
        await server.get_series_as_of("GDPC1", "1950-01-01", ctx)


@respx.mock
async def test_get_revision_history_walks_the_vintages(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    rows = [
        {
            "date": "2008-10-01",
            "value": "-3.8",
            "realtime_start": "2009-01-30",
            "realtime_end": "2009-02-26",
        },
        {
            "date": "2008-10-01",
            "value": "-6.2",
            "realtime_start": "2009-02-27",
            "realtime_end": "2009-03-25",
        },
        {
            "date": "2008-10-01",
            "value": "-6.3",
            "realtime_start": "2009-03-26",
            "realtime_end": "2009-06-24",
        },
        {
            "date": "2008-10-01",
            "value": "-8.5",
            "realtime_start": "2009-06-25",
            "realtime_end": "9999-12-31",
        },
    ]
    route = respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json={"observations": rows})
    )
    history = await server.get_revision_history("GDPC1", "2008-10-01", ctx)
    params = route.calls.last.request.url.params
    assert params["realtime_start"] == "1776-07-04"
    assert params["realtime_end"] == "9999-12-31"
    assert params["output_type"] == "1"
    assert history.initial_value == -3.8
    assert history.current_value == -8.5
    assert history.total_revision == -4.7
    assert len(history.steps) == 4
    assert history.steps[0].is_initial and history.steps[-1].is_current


@respx.mock
async def test_get_revision_history_no_observation_hints_period_start(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json={"observations": []})
    )
    with pytest.raises(FredError, match="period START"):
        await server.get_revision_history("GDPC1", "2008-12-31", ctx)


@respx.mock
async def test_get_vintage_dates_summary(ctx):
    dates = ["2009-01-30", "2009-02-27", "2009-03-26", "2009-06-25"]
    respx.get(f"{BASE_URL}/series/vintagedates").mock(
        return_value=httpx.Response(200, json={"vintage_dates": dates})
    )
    result = await server.get_vintage_dates("GDPC1", ctx)
    assert result.total_vintages == 4
    assert result.first_vintage == "2009-01-30"
    assert result.latest_vintage == "2009-06-25"
    assert result.vintage_dates[0] == "2009-06-25"  # most recent first
    assert result.truncated is False


@respx.mock
async def test_get_vintage_dates_caps_the_list(ctx):
    dates = [f"20{10 + i // 12:02d}-{i % 12 + 1:02d}-01" for i in range(70)]
    respx.get(f"{BASE_URL}/series/vintagedates").mock(
        return_value=httpx.Response(200, json={"vintage_dates": dates})
    )
    result = await server.get_vintage_dates("GDPC1", ctx)
    assert result.total_vintages == 70
    assert len(result.vintage_dates) == 60
    assert result.truncated is True
    assert result.first_vintage == dates[0]


@respx.mock
async def test_get_vintage_dates_unknown_series(ctx):
    respx.get(f"{BASE_URL}/series/vintagedates").mock(
        return_value=httpx.Response(200, json={"vintage_dates": []})
    )
    with pytest.raises(FredError, match="search_series"):
        await server.get_vintage_dates("NOPE", ctx)


@respx.mock
async def test_get_series_as_of_pins_metadata_to_the_vintage_too(ctx):
    meta_route = respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(
            200, json=series_payload(units="Billions of Chained 2000 Dollars")
        )
    )
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json=observations_payload([]))
    )
    result = await server.get_series_as_of("GDPC1", "2009-02-15", ctx)
    params = meta_route.calls.last.request.url.params
    assert params["realtime_start"] == "2009-02-15"
    assert params["realtime_end"] == "2009-02-15"
    assert result.units == "Billions of Chained 2000 Dollars"


@respx.mock
async def test_get_revision_history_caps_steps_and_flags_it(ctx):
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json=series_payload())
    )
    rows = [
        {
            "date": "2008-10-01",
            "value": str(-3.8 - i * 0.1),
            "realtime_start": f"20{10 + i // 12:02d}-{i % 12 + 1:02d}-01",
            "realtime_end": (
                f"20{10 + (i + 1) // 12:02d}-{(i + 1) % 12 + 1:02d}-01"
                if i < 69
                else "9999-12-31"
            ),
        }
        for i in range(70)
    ]
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(200, json={"observations": rows})
    )
    history = await server.get_revision_history("GDPC1", "2008-10-01", ctx)
    assert history.steps_truncated is True
    assert len(history.steps) == 60
    assert history.archive_starts == "2010-01-01"
    assert history.steps[0].is_initial  # initial kept
    assert history.steps[-1].is_current  # current kept
    assert history.current_value == history.steps[-1].value
