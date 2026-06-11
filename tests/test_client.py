"""FredClient: key handling, error surfacing, and the volatility-aware cache."""

import datetime as dt

import httpx
import pytest
import respx

from fred_mcp.fred_client import (
    _TTL_DEFAULT,
    _TTL_METADATA,
    _TTL_VINTAGE,
    BASE_URL,
    FredClient,
    FredError,
    MissingKeyError,
    _ttl_for,
)

TODAY = dt.date(2026, 6, 10)


async def test_missing_key_fails_fast_before_network(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    async with FredClient(api_key=None) as client:
        with pytest.raises(MissingKeyError, match="FRED_API_KEY"):
            await client.fred_json("/series", {"series_id": "GDPC1"})


@respx.mock
async def test_key_and_file_type_are_injected(fred):
    route = respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json={"seriess": []})
    )
    await fred.fred_json("/series", {"series_id": "GDPC1"})
    params = route.calls.last.request.url.params
    assert params["api_key"] == "test-key"
    assert params["file_type"] == "json"
    assert params["series_id"] == "GDPC1"


@respx.mock
async def test_fred_error_message_is_surfaced(fred):
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(
            400,
            json={
                "error_code": 400,
                "error_message": "Bad Request. The series does not exist.",
            },
        )
    )
    with pytest.raises(FredError, match="does not exist"):
        await fred.observations("NOPE")


@respx.mock
async def test_responses_are_cached(fred):
    route = respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(200, json={"seriess": []})
    )
    await fred.series("GDPC1")
    await fred.series("GDPC1")
    assert route.call_count == 1  # second read served from cache


def test_ttl_past_vintage_reads_are_long_lived():
    params = {"realtime_start": "2009-01-30", "realtime_end": "2009-01-30"}
    assert _ttl_for("/series/observations", params, TODAY) == _TTL_VINTAGE


def test_ttl_current_realtime_end_is_not_vintage():
    params = {"realtime_end": "9999-12-31"}
    assert _ttl_for("/series/observations", params, TODAY) == _TTL_DEFAULT


def test_ttl_today_is_not_vintage():
    params = {"realtime_end": TODAY.isoformat()}
    assert _ttl_for("/series/observations", params, TODAY) == _TTL_DEFAULT


def test_ttl_metadata_endpoints():
    assert _ttl_for("/series", {"series_id": "X"}, TODAY) == _TTL_METADATA
    assert _ttl_for("/series/search", {"search_text": "x"}, TODAY) == _TTL_METADATA
    assert _ttl_for("/series/observations", {"series_id": "X"}, TODAY) == _TTL_DEFAULT


@respx.mock
async def test_error_messages_never_leak_the_api_key(fred):
    # A WAF/edge can serve non-JSON 4xx pages; the URL echo carries api_key.
    respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(403, text="<html>Forbidden</html>")
    )
    with pytest.raises(FredError) as excinfo:
        await fred.series("GDPC1")
    assert "test-key" not in str(excinfo.value)


@respx.mock
async def test_not_found_messages_never_leak_the_api_key(fred):
    respx.get(f"{BASE_URL}/series").mock(return_value=httpx.Response(404))
    with pytest.raises(FredError) as excinfo:
        await fred.series("GDPC1")
    assert "test-key" not in str(excinfo.value)
    assert "REDACTED" in str(excinfo.value)


def test_ttl_yesterday_is_not_settled_enough():
    # FRED's data day is US Central; a one-day buffer avoids treating a
    # possibly-in-progress vintage day as immutable.
    yesterday = (TODAY - dt.timedelta(days=1)).isoformat()
    params = {"realtime_start": yesterday, "realtime_end": yesterday}
    assert _ttl_for("/series/observations", params, TODAY) == _TTL_DEFAULT


def test_ttl_two_days_ago_is_vintage():
    settled = (TODAY - dt.timedelta(days=2)).isoformat()
    params = {"realtime_start": settled, "realtime_end": settled}
    assert _ttl_for("/series/observations", params, TODAY) == _TTL_VINTAGE
