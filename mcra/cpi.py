"""Async CPI data fetching from FRED (US) and Eurostat (EU/UK/CH/JP).

Data flow per country:
    1. Check cache (skip if fresh)
    2. Fetch from primary API
    3. On failure, fall back to bundled CSV
    4. Save successful API responses to cache
"""

from __future__ import annotations

import asyncio
import csv
import os
from datetime import UTC, date, datetime
from importlib import resources

import httpx

from mcra import cache
from mcra.models import CURRENCY_COUNTRY_MAP, CPICacheEntry

# --- FRED (US CPI) ---

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = "CPIAUCNS"


async def _fetch_fred(
    client: httpx.AsyncClient,
    start: date,
    end: date,
) -> dict[str, float]:
    """Fetch US CPI from FRED. Requires FRED_API_KEY env var."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise OSError("FRED_API_KEY not set")

    resp = await client.get(
        FRED_BASE,
        params={
            "series_id": FRED_SERIES,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start.replace(day=1).isoformat(),
            "observation_end": end.isoformat(),
        },
    )
    resp.raise_for_status()
    data = resp.json()

    series: dict[str, float] = {}
    for obs in data.get("observations", []):
        if obs["value"] == ".":
            continue
        # FRED dates are first of month: "2023-03-01" -> "2023-03"
        month_key = obs["date"][:7]
        series[month_key] = float(obs["value"])
    return series


# --- Eurostat (HICP) ---

EUROSTAT_BASE = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0"
    "/data/prc_hicp_midx"
)


async def _fetch_eurostat(
    client: httpx.AsyncClient,
    country_code: str,
    start: date,
    end: date,
) -> dict[str, float]:
    """Fetch HICP index from Eurostat for a given country."""
    since = f"{start.year}-{start.month:02d}"
    until = f"{end.year}-{end.month:02d}"

    resp = await client.get(
        EUROSTAT_BASE,
        params={
            "format": "JSON",
            "lang": "EN",
            "coicop": "CP00",
            "unit": "I15",
            "geo": country_code,
            "sinceTimePeriod": since,
            "untilTimePeriod": until,
        },
    )
    resp.raise_for_status()
    data = resp.json()

    # JSON-stat: join value indices with time dimension
    values = data.get("value", {})
    time_idx = (
        data.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})
    )

    # Invert: {period: str_index}
    idx_to_period = {str(v): k for k, v in time_idx.items()}

    series: dict[str, float] = {}
    for str_idx, val in values.items():
        period = idx_to_period.get(str_idx)
        if period is not None and val is not None:
            series[period] = float(val)
    return series


# --- Bundled CSV fallback ---


def _load_fallback_csv() -> dict[str, dict[str, float]]:
    """Load bundled CPI CSV. Returns {country: {YYYY-MM: value}}."""
    result: dict[str, dict[str, float]] = {}
    csv_path = resources.files("mcra.data").joinpath("cpi_fallback.csv")
    text = csv_path.read_text(encoding="utf-8")
    for row in csv.DictReader(text.splitlines()):
        country = row["country"]
        month_key = row["date"][:7]  # "YYYY-MM"
        result.setdefault(country, {})[month_key] = float(row["index"])
    return result


# --- CPI month lookup ---


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _interpolate_cpi(series: dict[str, float], target_key: str) -> float | None:
    """Linear interpolation between two adjacent months if target is missing."""
    sorted_keys = sorted(series.keys())
    if not sorted_keys:
        return None

    # Find bracketing months
    prev_key = None
    next_key = None
    for k in sorted_keys:
        if k < target_key:
            prev_key = k
        elif k > target_key:
            next_key = k
            break

    if prev_key is None or next_key is None:
        return None

    # Simple linear interpolation
    return (series[prev_key] + series[next_key]) / 2


def _nearest_cpi(series: dict[str, float], target_key: str) -> float | None:
    """Return the value of the closest available month."""
    if not series:
        return None
    sorted_keys = sorted(series.keys())
    # Find the nearest key by string comparison (YYYY-MM sorts correctly)
    best = min(sorted_keys, key=lambda k: abs(_month_distance(k, target_key)))
    return series[best]


def _month_distance(a: str, b: str) -> int:
    """Signed distance in months between two YYYY-MM strings."""
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    return (ya * 12 + ma) - (yb * 12 + mb)


def get_cpi_values(
    series: dict[str, float],
    start_date: date,
    end_date: date,
) -> tuple[float, float]:
    """Extract CPI values for start and end months.

    Lookup order: exact month match → linear interpolation → nearest month.
    Raises ValueError if data is unavailable.
    """
    start_key = _month_key(start_date)
    end_key = _month_key(end_date)

    start_val = (
        series.get(start_key)
        or _interpolate_cpi(series, start_key)
        or _nearest_cpi(series, start_key)
    )
    end_val = (
        series.get(end_key)
        or _interpolate_cpi(series, end_key)
        or _nearest_cpi(series, end_key)
    )

    if start_val is None:
        raise ValueError(f"No CPI data for {start_key}")
    if end_val is None:
        raise ValueError(f"No CPI data for {end_key}")

    return start_val, end_val


# --- Main fetch orchestrator ---


async def fetch_cpi_for_currency(
    client: httpx.AsyncClient,
    currency: str,
    start_date: date,
    end_date: date,
    force_refresh: bool = False,
) -> tuple[dict[str, float], list[str]]:
    """Fetch CPI series for a currency's reference country.

    Returns (series_dict, warnings_list).
    """
    info = CURRENCY_COUNTRY_MAP[currency]
    country = info.country
    warnings: list[str] = []

    # 1. Check cache
    if not force_refresh:
        cached = cache.load_cpi_cache(country)
        if cached is not None and not cache.is_cpi_stale(cached):
            return cached.series, warnings

    # 2. Fetch from API
    series: dict[str, float] | None = None
    source = info.cpi_source

    try:
        if source == "FRED":
            series = await _fetch_fred(client, start_date, end_date)
        else:
            series = await _fetch_eurostat(client, country, start_date, end_date)
    except OSError:
        warnings.append("FRED_API_KEY not set. Using cached or fallback US CPI data.")
    except httpx.HTTPError as exc:
        warnings.append(f"API error fetching CPI for {country}: {exc}")

    # 3. Save to cache if we got data
    if series:
        entry = CPICacheEntry(
            country=country,
            source=source,
            last_updated=datetime.now(UTC),
            base_year="2015" if source == "Eurostat" else "1982-84",
            series=series,
        )
        cache.save_cpi_cache(entry)
        return series, warnings

    # 4. Try stale cache
    stale = cache.load_cpi_cache(country)
    if stale is not None:
        warnings.append(f"Using stale cached CPI for {country}.")
        return stale.series, warnings

    # 5. Fall back to bundled CSV
    fallback = _load_fallback_csv()
    if country in fallback:
        warnings.append(f"Using bundled fallback CPI for {country}.")
        return fallback[country], warnings

    raise ValueError(f"No CPI data available for {country} ({currency})")


async def fetch_all_cpi(
    client: httpx.AsyncClient,
    currencies: list[str],
    start_date: date,
    end_date: date,
    force_refresh: bool = False,
) -> tuple[dict[str, dict[str, float]], list[str]]:
    """Fetch CPI series for all requested currencies in parallel.

    Returns ({currency: series}, aggregated_warnings).
    """
    tasks = [
        fetch_cpi_for_currency(client, c, start_date, end_date, force_refresh)
        for c in currencies
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_series: dict[str, dict[str, float]] = {}
    all_warnings: list[str] = []

    for currency, result in zip(currencies, results, strict=True):
        if isinstance(result, BaseException):
            raise result
        assert isinstance(result, tuple)
        series, warns = result
        all_series[currency] = series
        all_warnings.extend(warns)

    return all_series, all_warnings
