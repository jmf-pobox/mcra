"""CLI entry point for MCRA."""

from __future__ import annotations

import asyncio
import sys
from datetime import date

import click
import httpx

from mcra import cache, calculator, cpi, formatters, fx
from mcra.models import (
    CURRENCY_COUNTRY_MAP,
    SUPPORTED_CURRENCIES,
    AnalysisPeriod,
    AnalysisResult,
    CurrencyResult,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise click.BadParameter(
            f"Invalid date format: {value!r}. Use YYYY-MM-DD."
        ) from exc


def _validate_currencies(raw: str) -> list[str]:
    codes = [c.strip().upper() for c in raw.split(",") if c.strip()]
    for c in codes:
        if c not in CURRENCY_COUNTRY_MAP:
            supported = ", ".join(SUPPORTED_CURRENCIES)
            raise click.BadParameter(
                f"Currency {c!r} not supported. Supported: {supported}"
            )
    return codes


async def _run_analysis(
    start_date: date,
    end_date: date,
    start_value: float,
    end_value: float,
    base_currency: str,
    currencies: list[str],
    show_cagr: bool,
    force_refresh: bool,
) -> AnalysisResult:
    years = calculator.years_between(start_date, end_date)
    period = AnalysisPeriod(start_date=start_date, end_date=end_date, years=years)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch FX rates and CPI data in parallel
        fx_task = fx.fetch_rate_pair(
            client, start_date, end_date, base_currency, currencies
        )
        cpi_task = cpi.fetch_all_cpi(
            client, currencies, start_date, end_date, force_refresh
        )

        (start_rates, end_rates), (cpi_series, warnings) = await asyncio.gather(
            fx_task, cpi_task
        )

    results: list[CurrencyResult] = []

    for currency in currencies:
        fx_start = start_rates[currency]
        fx_end = end_rates[currency]

        local_start = calculator.convert_to_currency(start_value, fx_start)
        local_end = calculator.convert_to_currency(end_value, fx_end)

        nom = calculator.nominal_return(local_start, local_end)
        fx_chg = calculator.fx_change(fx_start, fx_end)

        # CPI lookup
        series = cpi_series[currency]
        cpi_start_val, cpi_end_val = cpi.get_cpi_values(series, start_date, end_date)
        infl = calculator.cumulative_inflation(cpi_start_val, cpi_end_val)
        real = calculator.real_return(nom, infl)
        discounted = calculator.discount_for_inflation(local_end, infl)

        # CAGR — real always computed; nominal only with --cagr
        ann_inf = calculator.annualized_inflation(cpi_start_val, cpi_end_val, years)
        nom_cagr_val = calculator.nominal_cagr(local_start, local_end, years)
        real_cagr_val = calculator.real_cagr(nom_cagr_val, ann_inf)

        nom_cagr = nom_cagr_val if show_cagr else None

        results.append(
            CurrencyResult(
                currency=currency,
                country=CURRENCY_COUNTRY_MAP[currency].country,
                start_value=local_start,
                end_value=local_end,
                fx_rate_start=fx_start,
                fx_rate_end=fx_end,
                fx_change_pct=fx_chg,
                nominal_return_pct=nom,
                cumulative_inflation_pct=infl,
                real_return_pct=real,
                discounted_end_value=discounted,
                real_cagr_pct=real_cagr_val,
                nominal_cagr_pct=nom_cagr,
            )
        )

    return AnalysisResult(
        period=period,
        base_currency=base_currency,
        start_value=start_value,
        end_value=end_value,
        results=results,
        warnings=warnings,
    )


@click.command()
@click.option("--start-date", required=False, help="Start date (YYYY-MM-DD)")
@click.option("--end-date", required=False, help="End date (YYYY-MM-DD)")
@click.option(
    "--start-value", required=False, type=float, help="Portfolio value at start"
)
@click.option("--end-value", required=False, type=float, help="Portfolio value at end")
@click.option(
    "--base-currency",
    default="USD",
    help="Base currency of portfolio values (default: USD)",
)
@click.option(
    "--currencies", default="USD,EUR,GBP,CHF", help="Comma-separated target currencies"
)
@click.option("--cagr", is_flag=True, help="Include CAGR in output")
@click.option(
    "--output",
    "output_format",
    default="table",
    type=click.Choice(["table", "json", "csv"]),
    help="Output format",
)
@click.option(
    "--cache-status",
    "show_cache_status",
    is_flag=True,
    help="Show cache file locations and freshness",
)
@click.option("--refresh-cache", is_flag=True, help="Force refresh of cached CPI data")
def main(
    start_date: str | None,
    end_date: str | None,
    start_value: float | None,
    end_value: float | None,
    base_currency: str,
    currencies: str,
    cagr: bool,
    output_format: str,
    show_cache_status: bool,
    refresh_cache: bool,
) -> None:
    """Multi-Currency Real Return Analyzer.

    Calculates portfolio returns from multiple currency perspectives,
    adjusted for local inflation to produce real (purchasing-power-adjusted) returns.
    """
    # Handle cache-only commands
    if show_cache_status:
        entries = cache.cache_status()
        if not entries:
            click.echo("No cache files found.")
        else:
            click.echo("Cache files:")
            for e in entries:
                name = e["file"]
                size = e["size_bytes"]
                mod = e["modified"]
                click.echo(f"  {name:20s}  {size:>8d} bytes  modified {mod}")
            click.echo(f"\nCache directory: {cache.CACHE_DIR}")
        return

    if refresh_cache and not start_date:
        count = cache.clear_cache()
        click.echo(f"Cleared {count} cache file(s).")
        return

    # Show help if no analysis options provided
    if not start_date and not end_date and start_value is None and end_value is None:
        click.echo(click.get_current_context().get_help())
        return

    # Validate required options for analysis
    missing = []
    if not start_date:
        missing.append("--start-date")
    if not end_date:
        missing.append("--end-date")
    if start_value is None:
        missing.append("--start-value")
    if end_value is None:
        missing.append("--end-value")
    if missing:
        click.echo(f"Error: Missing required options: {', '.join(missing)}", err=True)
        sys.exit(1)

    if start_value <= 0:  # type: ignore[operator]
        click.echo("Error: --start-value must be positive.", err=True)
        sys.exit(1)

    if end_value <= 0:  # type: ignore[operator]
        click.echo("Error: --end-value must be positive.", err=True)
        sys.exit(1)

    sd = _parse_date(start_date)  # type: ignore[arg-type]
    ed = _parse_date(end_date)  # type: ignore[arg-type]

    if ed > date.today():
        click.echo("Error: End date cannot be in the future.", err=True)
        sys.exit(1)

    if ed <= sd:
        click.echo("Error: End date must be after start date.", err=True)
        sys.exit(1)

    currency_list = _validate_currencies(currencies)
    base = base_currency.strip().upper()
    if base not in CURRENCY_COUNTRY_MAP:
        supported = ", ".join(SUPPORTED_CURRENCIES)
        click.echo(
            f"Error: Base currency {base!r} not supported. Supported: {supported}",
            err=True,
        )
        sys.exit(1)

    # Ensure base currency is in the list
    if base not in currency_list:
        currency_list.insert(0, base)

    assert start_value is not None
    assert end_value is not None

    try:
        result = asyncio.run(
            _run_analysis(
                sd,
                ed,
                start_value,
                end_value,
                base,
                currency_list,
                cagr,
                refresh_cache,
            )
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Format and output
    if output_format == "json":
        click.echo(formatters.format_json(result, show_cagr=cagr))
    elif output_format == "csv":
        click.echo(formatters.format_csv(result, show_cagr=cagr), nl=False)
    else:
        click.echo(formatters.format_table(result, show_cagr=cagr), nl=False)


if __name__ == "__main__":
    main()
