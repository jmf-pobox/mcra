"""Data models for MCRA results and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


CURRENCY_COUNTRY_MAP: dict[str, CurrencyInfo] = {}


@dataclass(slots=True)
class CurrencyInfo:
    code: str
    country: str
    country_name: str
    cpi_source: str
    symbol: str


@dataclass(slots=True)
class CurrencyResult:
    currency: str
    country: str
    start_value: float
    end_value: float
    fx_rate_start: float
    fx_rate_end: float
    fx_change_pct: float
    nominal_return_pct: float
    cumulative_inflation_pct: float
    real_return_pct: float
    discounted_end_value: float = 0.0
    real_cagr_pct: float = 0.0
    nominal_cagr_pct: float | None = None


@dataclass(slots=True)
class AnalysisPeriod:
    start_date: date
    end_date: date
    years: float


@dataclass(slots=True)
class AnalysisResult:
    period: AnalysisPeriod
    base_currency: str
    start_value: float
    end_value: float
    results: list[CurrencyResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CPICacheEntry:
    country: str
    source: str
    last_updated: datetime
    base_year: str
    series: dict[str, float]  # "YYYY-MM" -> index value


# --- Currency registry ---

def _build_currency_map() -> dict[str, CurrencyInfo]:
    entries = [
        CurrencyInfo("USD", "US", "United States", "FRED", "$"),
        CurrencyInfo("EUR", "DE", "Germany", "Eurostat", "€"),
        CurrencyInfo("GBP", "UK", "United Kingdom", "Eurostat", "£"),
        CurrencyInfo("CHF", "CH", "Switzerland", "Eurostat", "Fr"),
        CurrencyInfo("JPY", "JP", "Japan", "Eurostat", "¥"),
    ]
    return {e.code: e for e in entries}


CURRENCY_COUNTRY_MAP = _build_currency_map()
SUPPORTED_CURRENCIES = list(CURRENCY_COUNTRY_MAP.keys())
