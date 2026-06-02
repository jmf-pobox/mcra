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
        with pytest.raises(OSError, match="FRED_API_KEY"):
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
async def test_fetch_ons(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(
        json={
            "months": [
                {"date": "2023 MAR", "value": "128.2"},
                {"date": "2023 APR", "value": "130.4"},
                {"date": "2023 MAY", "value": "131.0"},
            ]
        },
    )

    async with httpx.AsyncClient() as client:
        series = await cpi._fetch_ons(client, date(2023, 3, 1), date(2023, 5, 31))

    assert series["2023-03"] == pytest.approx(128.2)
    assert series["2023-04"] == pytest.approx(130.4)
    assert series["2023-05"] == pytest.approx(131.0)


@pytest.mark.asyncio
async def test_fetch_ons_filters_date_range(httpx_mock: pytest_httpx.HTTPXMock):
    httpx_mock.add_response(
        json={
            "months": [
                {"date": "2022 DEC", "value": "125.0"},
                {"date": "2023 JAN", "value": "126.0"},
                {"date": "2023 FEB", "value": "127.0"},
            ]
        },
    )

    async with httpx.AsyncClient() as client:
        series = await cpi._fetch_ons(client, date(2023, 1, 1), date(2023, 2, 28))

    assert "2022-12" not in series
    assert series["2023-01"] == pytest.approx(126.0)
    assert series["2023-02"] == pytest.approx(127.0)


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


# --- Seasonal-trend composite estimation ---


# Synthetic 3-year CPI series with a clear seasonal pattern.
# Each October dips relative to September, each January jumps.
def _make_seasonal_series() -> dict[str, float]:
    """Build a synthetic series 2021-01 through 2024-09 with ~0.3%/mo trend."""
    base = 100.0
    monthly_trend = 1.003
    seasonal_shape = {
        1: 1.005,
        2: 1.004,
        3: 1.003,
        4: 1.002,
        5: 1.001,
        6: 1.002,
        7: 1.003,
        8: 1.004,
        9: 1.003,
        10: 0.998,
        11: 0.997,
        12: 1.001,
    }
    series: dict[str, float] = {}
    val = base
    for year in range(2021, 2025):
        end_month = 9 if year == 2024 else 12
        for month in range(1, end_month + 1):
            key = f"{year}-{month:02d}"
            ratio = seasonal_shape[month] * monthly_trend / 1.003
            val *= ratio
            series[key] = round(val, 3)
    return series


class TestSeasonalRatio:
    def test_returns_ratio_for_known_month(self):
        series = _make_seasonal_series()
        ratio = cpi._seasonal_ratio(series, month=10, lookback_years=3)
        assert ratio is not None
        assert ratio < 1.0  # October dips in our synthetic data

    def test_january_jump(self):
        series = _make_seasonal_series()
        ratio = cpi._seasonal_ratio(series, month=1, lookback_years=3)
        assert ratio is not None
        assert ratio > 1.0

    def test_respects_lookback_limit(self):
        series = _make_seasonal_series()
        r3 = cpi._seasonal_ratio(series, month=6, lookback_years=3)
        r1 = cpi._seasonal_ratio(series, month=6, lookback_years=1)
        assert r3 is not None and r1 is not None
        # Both should be close (stable pattern) but not identical (different years)
        assert r3 == pytest.approx(r1, rel=0.01)

    def test_returns_none_for_missing_month(self):
        series = {"2023-03": 100.0, "2023-05": 102.0}
        assert cpi._seasonal_ratio(series, month=4) is None


class TestTrendRatio:
    def test_trailing_trend(self):
        series = _make_seasonal_series()
        ratio = cpi._trend_ratio(series, before_key="2024-09", window=3)
        assert ratio is not None
        assert 0.99 < ratio < 1.01

    def test_window_limits_scope(self):
        series = {
            "2024-01": 100.0,
            "2024-02": 101.0,
            "2024-03": 101.5,
            "2024-04": 102.0,
        }
        r2 = cpi._trend_ratio(series, "2024-04", window=2)
        r3 = cpi._trend_ratio(series, "2024-04", window=3)
        assert r2 is not None and r3 is not None
        # window=2 uses only Mar/Apr and Feb/Mar ratios
        assert r2 != pytest.approx(r3, rel=1e-6)

    def test_skips_non_consecutive_months(self):
        series = {"2024-01": 100.0, "2024-03": 103.0, "2024-04": 104.0}
        ratio = cpi._trend_ratio(series, "2024-04", window=3)
        assert ratio is not None
        # Only one consecutive pair (Mar→Apr), so window=3 still uses it
        assert ratio == pytest.approx(104.0 / 103.0, rel=1e-6)

    def test_returns_none_for_single_point(self):
        assert cpi._trend_ratio({"2024-01": 100.0}, "2024-01") is None


class TestFillEstimatedMonths:
    def test_fills_end_of_series_gap(self):
        series = _make_seasonal_series()  # ends at 2024-09
        filled, estimated = cpi.fill_estimated_months(
            series, date(2024, 1, 1), date(2024, 12, 31)
        )
        assert "2024-10" in filled
        assert "2024-11" in filled
        assert "2024-12" in filled
        assert estimated == ["2024-10", "2024-11", "2024-12"]

    def test_october_estimate_reflects_seasonal_dip(self):
        """October's seasonal dip pulls the estimate below a pure-trend projection."""
        series = _make_seasonal_series()
        filled, _ = cpi.fill_estimated_months(
            series, date(2024, 1, 1), date(2024, 12, 31)
        )
        trend_only = cpi._trend_ratio(series, "2024-09", window=3)
        assert trend_only is not None
        pure_trend_oct = series["2024-09"] * trend_only
        assert filled["2024-10"] < pure_trend_oct

    def test_fills_interior_gap(self):
        series = _make_seasonal_series()
        del series["2023-06"]
        filled, estimated = cpi.fill_estimated_months(
            series, date(2023, 1, 1), date(2023, 12, 31)
        )
        assert "2023-06" in filled
        assert "2023-06" in estimated
        assert filled["2023-05"] < filled["2023-06"] < filled["2023-07"]

    def test_no_gaps_returns_empty_estimated(self):
        series = _make_seasonal_series()
        filled, estimated = cpi.fill_estimated_months(
            series, date(2022, 1, 1), date(2022, 12, 31)
        )
        assert estimated == []
        assert filled == series  # no mutations

    def test_does_not_mutate_original(self):
        series = _make_seasonal_series()
        original_keys = set(series.keys())
        cpi.fill_estimated_months(series, date(2024, 1, 1), date(2024, 12, 31))
        assert set(series.keys()) == original_keys

    def test_real_data_replaces_estimates(self):
        """Simulates cache refresh: real value present → no estimation."""
        series = _make_seasonal_series()
        # First run: 2024-10 missing → estimated
        _, est1 = cpi.fill_estimated_months(
            series, date(2024, 1, 1), date(2024, 12, 31)
        )
        assert "2024-10" in est1

        # Second run: real data arrives for 2024-10
        series["2024-10"] = 108.5
        _, est2 = cpi.fill_estimated_months(
            series, date(2024, 1, 1), date(2024, 12, 31)
        )
        assert "2024-10" not in est2


class TestApplySupplemental:
    def test_fills_missing_month(self):
        series: cpi.CPISeries = {"2025-09": 324.0, "2025-11": 326.0}
        filled, applied = cpi._apply_supplemental(series, "US")
        assert "2025-10" in filled
        assert filled["2025-10"] == pytest.approx(325.604)
        assert "2025-10" in applied

    def test_does_not_overwrite_real_data(self):
        series: cpi.CPISeries = {"2025-09": 324.0, "2025-10": 999.0, "2025-11": 326.0}
        filled, applied = cpi._apply_supplemental(series, "US")
        assert filled["2025-10"] == pytest.approx(999.0)
        assert "2025-10" not in applied

    def test_no_patches_for_unknown_country(self):
        series: cpi.CPISeries = {"2025-01": 100.0}
        filled, applied = cpi._apply_supplemental(series, "XX")
        assert filled == series
        assert applied == []


class TestMonthKeyHelpers:
    def test_prev_month_key(self):
        assert cpi._prev_month_key("2024-01") == "2023-12"
        assert cpi._prev_month_key("2024-06") == "2024-05"

    def test_next_month_key(self):
        assert cpi._next_month_key("2024-12") == "2025-01"
        assert cpi._next_month_key("2024-06") == "2024-07"
