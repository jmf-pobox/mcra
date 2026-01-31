"""Tests for FX rate fetching."""

from datetime import date

import httpx
import pytest
import pytest_httpx

from mcra import fx


@pytest.fixture(autouse=True)
def clear_fx_cache(tmp_path, monkeypatch):
    """Redirect cache to tmp dir so tests don't pollute real cache."""
    monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
    monkeypatch.setattr("mcra.cache._FX_PATH", tmp_path / "fx_cache.json")


@pytest.mark.asyncio
async def test_fetch_rates(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(
        url="https://api.frankfurter.dev/v1/2023-03-31?base=USD&symbols=EUR%2CGBP",
        json={
            "base": "USD",
            "date": "2023-03-31",
            "rates": {"EUR": 0.9203, "GBP": 0.8101},
        },
    )

    async with httpx.AsyncClient() as client:
        rates = await fx.fetch_rates(
            client, date(2023, 3, 31), "USD", ["USD", "EUR", "GBP"]
        )

    assert rates["USD"] == 1.0
    assert rates["EUR"] == pytest.approx(0.9203, rel=1e-4)
    assert rates["GBP"] == pytest.approx(0.8101, rel=1e-4)


@pytest.mark.asyncio
async def test_fetch_rates_base_only():
    """Requesting only the base currency needs no API call."""
    async with httpx.AsyncClient() as client:
        rates = await fx.fetch_rates(client, date(2023, 3, 31), "USD", ["USD"])

    assert rates == {"USD": 1.0}


@pytest.mark.asyncio
async def test_fetch_rates_caches(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(
        json={
            "base": "USD",
            "date": "2023-03-31",
            "rates": {"EUR": 0.9203},
        },
    )

    async with httpx.AsyncClient() as client:
        # First call hits API
        rates1 = await fx.fetch_rates(
            client, date(2023, 3, 31), "USD", ["USD", "EUR"]
        )
        # Second call should use cache (no second HTTP mock needed)
        rates2 = await fx.fetch_rates(
            client, date(2023, 3, 31), "USD", ["USD", "EUR"]
        )

    assert rates1["EUR"] == rates2["EUR"]


@pytest.mark.asyncio
async def test_fetch_rate_pair(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(
        url="https://api.frankfurter.dev/v1/2023-03-31?base=USD&symbols=EUR",
        json={"base": "USD", "date": "2023-03-31", "rates": {"EUR": 0.92}},
    )
    httpx_mock.add_response(
        url="https://api.frankfurter.dev/v1/2026-01-28?base=USD&symbols=EUR",
        json={"base": "USD", "date": "2026-01-28", "rates": {"EUR": 0.83}},
    )

    async with httpx.AsyncClient() as client:
        start_rates, end_rates = await fx.fetch_rate_pair(
            client, date(2023, 3, 31), date(2026, 1, 28), "USD", ["USD", "EUR"]
        )

    assert start_rates["EUR"] == pytest.approx(0.92)
    assert end_rates["EUR"] == pytest.approx(0.83)
