"""Output formatters for table, JSON, and CSV."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from mcra.models import CURRENCY_COUNTRY_MAP, AnalysisResult


def _fmt_pct(val: float, plus_sign: bool = True) -> str:
    """Format a decimal as a percentage with 1 decimal place."""
    pct = val * 100
    if plus_sign and pct > 0:
        return f"+{pct:.1f}%"
    return f"{pct:.1f}%"


def _fmt_number(value: float) -> str:
    """Format a number with K/M/B suffix, keeping max 3 digits left of the decimal."""
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_val >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


def _fmt_currency_value(value: float, currency: str) -> str:
    """Format a value with the currency symbol and K/M suffix."""
    symbol = CURRENCY_COUNTRY_MAP.get(currency, None)
    prefix = symbol.symbol if symbol else f"{currency} "
    return f"{prefix}{_fmt_number(value)}"


def format_table(result: AnalysisResult, show_cagr: bool = False) -> str:
    """Format results as a Rich table rendered to string."""
    buf = io.StringIO()
    rich_console = Console(file=buf, width=120, no_color=True)

    p = result.period
    header = (
        f"Multi-Currency Real Return Analysis\n"
        f"===================================\n"
        f"Period: {p.start_date} → {p.end_date} ({p.years:.2f} years)\n"
        f"Base currency: {result.base_currency}\n"
    )

    table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    table.add_column("Currency", style="bold")
    table.add_column("Start Value", justify="right")
    table.add_column("End Value", justify="right")
    table.add_column("Disc. Value", justify="right")
    table.add_column("Nominal", justify="right")
    table.add_column("Real", justify="right")
    table.add_column("Real CAGR", justify="right")
    table.add_column("FX Δ", justify="right")
    table.add_column("Inflation", justify="right")
    if show_cagr:
        table.add_column("Nom CAGR", justify="right")

    for r in result.results:
        fx_str = (
            "—" if r.currency == result.base_currency else _fmt_pct(r.fx_change_pct)
        )
        row = [
            r.currency,
            _fmt_currency_value(r.start_value, r.currency),
            _fmt_currency_value(r.end_value, r.currency),
            _fmt_currency_value(r.discounted_end_value, r.currency),
            _fmt_pct(r.nominal_return_pct),
            _fmt_pct(r.real_return_pct),
            _fmt_pct(r.real_cagr_pct),
            fx_str,
            _fmt_pct(r.cumulative_inflation_pct, plus_sign=False),
        ]
        if show_cagr:
            row.append(
                _fmt_pct(r.nominal_cagr_pct) if r.nominal_cagr_pct is not None else "—"
            )
        table.add_row(*row)

    rich_console.print(header, end="")
    rich_console.print(table)

    footer = "\nData sources: FX via Frankfurter, CPI via Eurostat/FRED"
    if result.warnings:
        footer += "\n\nWarnings:"
        for w in result.warnings:
            footer += f"\n  ⚠ {w}"
    rich_console.print(footer)

    return buf.getvalue()


def format_json(result: AnalysisResult, show_cagr: bool = False) -> str:
    """Format results as JSON."""
    data: dict[str, Any] = {
        "period": {
            "start_date": result.period.start_date.isoformat(),
            "end_date": result.period.end_date.isoformat(),
            "years": round(result.period.years, 2),
        },
        "base_currency": result.base_currency,
        "results": [],
        "data_sources": {
            "fx": "Frankfurter API",
            "cpi": {},
        },
    }

    for r in result.results:
        entry: dict[str, Any] = {
            "currency": r.currency,
            "country": r.country,
            "start_value": round(r.start_value, 2),
            "end_value": round(r.end_value, 2),
            "discounted_end_value": round(r.discounted_end_value, 2),
            "fx_rate_start": round(r.fx_rate_start, 4),
            "fx_rate_end": round(r.fx_rate_end, 4),
            "fx_change_pct": round(r.fx_change_pct * 100, 2),
            "nominal_return_pct": round(r.nominal_return_pct * 100, 2),
            "cumulative_inflation_pct": round(r.cumulative_inflation_pct * 100, 2),
            "real_return_pct": round(r.real_return_pct * 100, 2),
            "real_cagr_pct": round(r.real_cagr_pct * 100, 2),
        }
        if show_cagr:
            entry["nominal_cagr_pct"] = (
                round(r.nominal_cagr_pct * 100, 2)
                if r.nominal_cagr_pct is not None
                else None
            )

        data["results"].append(entry)

        info = CURRENCY_COUNTRY_MAP.get(r.currency)
        if info:
            data["data_sources"]["cpi"][info.country] = info.cpi_source

    if result.warnings:
        data["warnings"] = result.warnings

    return json.dumps(data, indent=2)


def format_csv(result: AnalysisResult, show_cagr: bool = False) -> str:
    """Format results as CSV."""
    buf = io.StringIO()
    fields = [
        "currency",
        "country",
        "start_value",
        "end_value",
        "discounted_end_value",
        "fx_rate_start",
        "fx_rate_end",
        "fx_change_pct",
        "nominal_return_pct",
        "cumulative_inflation_pct",
        "real_return_pct",
        "real_cagr_pct",
    ]
    if show_cagr:
        fields.append("nominal_cagr_pct")

    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()

    for r in result.results:
        row: dict[str, str] = {
            "currency": r.currency,
            "country": r.country,
            "start_value": f"{r.start_value:.2f}",
            "end_value": f"{r.end_value:.2f}",
            "discounted_end_value": f"{r.discounted_end_value:.2f}",
            "fx_rate_start": f"{r.fx_rate_start:.4f}",
            "fx_rate_end": f"{r.fx_rate_end:.4f}",
            "fx_change_pct": f"{r.fx_change_pct * 100:.2f}",
            "nominal_return_pct": f"{r.nominal_return_pct * 100:.2f}",
            "cumulative_inflation_pct": f"{r.cumulative_inflation_pct * 100:.2f}",
            "real_return_pct": f"{r.real_return_pct * 100:.2f}",
            "real_cagr_pct": f"{r.real_cagr_pct * 100:.2f}",
        }
        if show_cagr:
            row["nominal_cagr_pct"] = (
                f"{r.nominal_cagr_pct * 100:.2f}"
                if r.nominal_cagr_pct is not None
                else ""
            )
        writer.writerow(row)

    return buf.getvalue()
