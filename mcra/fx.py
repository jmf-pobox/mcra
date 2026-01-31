"""Async FX rate client using the Frankfurter API.

Frankfurter returns rates for the requested date or the nearest prior business day.
No API key required. Base URL: https://api.frankfurter.dev/v1
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from mcra import cache

BASE_URL = "https://api.frankfurter.dev/v1"


async def fetch_rates(
    client: httpx.AsyncClient,
    query_date: date,
    base: str,
    symbols: list[str],
) -> dict[str, float]:
    """Fetch FX rates for a single date.

    Returns a dict mapping currency code to rate (units of target per 1 base).
    The base currency itself is included with rate 1.0.
    """
    # Filter out base currency from API request
    remote_symbols = [s for s in symbols if s != base]

    rates: dict[str, float] = {base: 1.0}
    if not remote_symbols:
        return rates

    date_str = query_date.isoformat()

    # Check cache first
    all_cached = True
    for sym in remote_symbols:
        cached = cache.load_fx_rate(date_str, base, sym)
        if cached is not None:
            rates[sym] = cached
        else:
            all_cached = False

    if all_cached:
        return rates

    # Fetch from API
    resp = await client.get(
        f"{BASE_URL}/{date_str}",
        params={"base": base, "symbols": ",".join(remote_symbols)},
    )
    resp.raise_for_status()
    data = resp.json()

    fetched_rates = data.get("rates", {})
    cache.save_fx_rates(date_str, base, fetched_rates)

    rates.update(fetched_rates)
    return rates


async def fetch_rate_pair(
    client: httpx.AsyncClient,
    start_date: date,
    end_date: date,
    base: str,
    symbols: list[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Fetch start and end FX rates in parallel.

    Returns (start_rates, end_rates) dicts.
    """
    start_rates, end_rates = await asyncio.gather(
        fetch_rates(client, start_date, base, symbols),
        fetch_rates(client, end_date, base, symbols),
    )
    return start_rates, end_rates
