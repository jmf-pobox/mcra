"""Tests for CPI data fetching and lookup."""

from datetime import date

import httpx
import pytest
import pytest_httpx

from mcra import cpi


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Redirect cache to tmp dir."""
    monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
    monkeypatch.setattr("mcra.cache._FX_PATH", tmp_path / "fx_cache.json")


class TestGetCpiValues:
    def test_exact_match(self):
        series = {"2023-03": 301.836, "2026-01": 324.0}
        start, end = cpi.get_cpi_values(series, date(2023, 3, 31), date(2026, 1, 28))
        assert start == pytest.approx(301.836)
        assert end == pytest.approx(324.0)

    def test_interpolation(self):
        series = {"2023-02": 100.0, "2023-04": 104.0}
        start, end = cpi.get_cpi_values(series, date(2023, 3, 15), date(2023, 4, 15))
        # 2023-03 interpolated as midpoint of Feb and Apr = 102.0
        assert start == pytest.approx(102.0)
        assert end == pytest.approx(104.0)

    def test_nearest_fallback(self):
        """When only one month exists, nearest-month fallback uses it."""
        series = {"2023-01": 100.0}
        start, end = cpi.get_cpi_values(series, date(2024, 6, 1), date(2025, 1, 1))
        assert start == 100.0
        assert end == 100.0

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No CPI data"):
            cpi.get_cpi_values({}, date(2024, 6, 1), date(2025, 1, 1))


class TestLoadFallbackCsv:
    def test_loads_all_countries(self):
        data = cpi._load_fallback_csv()
        assert "US" in data
        assert "DE" in data
        assert "UK" in data
        assert "CH" in data
        assert "JP" in data

    def test_has_expected_keys(self):
        data = cpi._load_fallback_csv()
        assert "2023-03" in data["US"]
        assert "2023-03" in data["DE"]


@pytest.mark.asyncio
async def test_fetch_fred(httpx_mock: pytest_httpx.HTTPXMock, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    httpx_mock.add_response(
        json={
            "observations": [
                {"date": "2023-03-01", "value": "301.836"},
                {"date": "2023-04-01", "value": "302.918"},
            ]
        },
    )

    async with httpx.AsyncClient() as client:
        series = await cpi._fetch_fred(client, date(2023, 3, 1), date(2023, 4, 30))

    assert series["2023-03"] == pytest.approx(301.836)
    assert series["2023-04"] == pytest.approx(302.918)


@pytest.mark.asyncio
async def test_fetch_fred_no_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    async with httpx.AsyncClient() as client:
        with pytest.raises(EnvironmentError, match="FRED_API_KEY"):
            await cpi._fetch_fred(client, date(2023, 3, 1), date(2023, 4, 30))


@pytest.mark.asyncio
async def test_fetch_eurostat(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(
        json={
            "value": {"0": 118.9, "1": 119.4},
            "dimension": {
                "time": {"category": {"index": {"2023-03": 0, "2023-04": 1}}}
            },
        },
    )

    async with httpx.AsyncClient() as client:
        series = await cpi._fetch_eurostat(
            client, "DE", date(2023, 3, 1), date(2023, 4, 30)
        )

    assert series["2023-03"] == pytest.approx(118.9)
    assert series["2023-04"] == pytest.approx(119.4)


@pytest.mark.asyncio
async def test_fallback_on_api_failure(httpx_mock: pytest_httpx.HTTPXMock, monkeypatch):
    """If API fails and no cache, should fall back to bundled CSV."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    async with httpx.AsyncClient() as client:
        series, warnings = await cpi.fetch_cpi_for_currency(
            client, "USD", date(2023, 3, 1), date(2023, 12, 31)
        )

    assert len(series) > 0
    assert any("FRED_API_KEY" in w or "fallback" in w.lower() for w in warnings)
