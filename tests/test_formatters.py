"""Tests for output formatters."""

from __future__ import annotations

import json
from datetime import date

from mcra.formatters import (
    _fmt_currency_value,
    _fmt_number,
    _fmt_pct,
    format_csv,
    format_json,
    format_table,
)
from mcra.models import AnalysisPeriod, AnalysisResult, CurrencyResult


def _make_result(show_cagr: bool = False) -> AnalysisResult:
    period = AnalysisPeriod(
        start_date=date(2023, 3, 31),
        end_date=date(2026, 1, 31),
        years=2.84,
    )
    usd = CurrencyResult(
        currency="USD",
        country="US",
        start_value=10000.0,
        end_value=12064.0,
        fx_rate_start=1.0,
        fx_rate_end=1.0,
        fx_change_pct=0.0,
        nominal_return_pct=0.2064,
        cumulative_inflation_pct=0.074,
        real_return_pct=0.1233,
        discounted_end_value=11233.0,
        real_cagr_pct=0.042,
        nominal_cagr_pct=0.068 if show_cagr else None,
    )
    eur = CurrencyResult(
        currency="EUR",
        country="DE",
        start_value=9200.0,
        end_value=10120.0,
        fx_rate_start=0.9200,
        fx_rate_end=0.8390,
        fx_change_pct=-0.088,
        nominal_return_pct=0.10,
        cumulative_inflation_pct=0.062,
        real_return_pct=0.036,
        discounted_end_value=9530.0,
        real_cagr_pct=0.013,
        nominal_cagr_pct=0.033 if show_cagr else None,
    )
    return AnalysisResult(
        period=period,
        base_currency="USD",
        start_value=10000.0,
        end_value=12064.0,
        results=[usd, eur],
        warnings=["Test warning."],
    )


class TestFmtNumber:
    def test_under_thousand(self) -> None:
        assert _fmt_number(500.0) == "500.00"

    def test_thousands(self) -> None:
        assert _fmt_number(10000.0) == "10.00K"

    def test_millions(self) -> None:
        assert _fmt_number(1500000.0) == "1.50M"

    def test_billions(self) -> None:
        assert _fmt_number(2060000000.0) == "2.06B"

    def test_small_value(self) -> None:
        assert _fmt_number(0.99) == "0.99"


class TestFmtPct:
    def test_positive(self) -> None:
        assert _fmt_pct(0.232) == "+23.2%"

    def test_negative(self) -> None:
        assert _fmt_pct(-0.05) == "-5.0%"

    def test_no_plus_sign(self) -> None:
        assert _fmt_pct(0.074, plus_sign=False) == "7.4%"

    def test_zero(self) -> None:
        assert _fmt_pct(0.0) == "0.0%"


class TestFmtCurrencyValue:
    def test_usd(self) -> None:
        assert _fmt_currency_value(10000.0, "USD") == "$10.00K"

    def test_eur(self) -> None:
        assert _fmt_currency_value(500.0, "EUR") == "€500.00"

    def test_chf(self) -> None:
        assert _fmt_currency_value(14210.0, "CHF") == "Fr14.21K"

    def test_unknown_currency(self) -> None:
        assert _fmt_currency_value(100.0, "XYZ") == "XYZ 100.00"


class TestFormatTable:
    def test_contains_header(self) -> None:
        result = _make_result()
        output = format_table(result)
        assert "Multi-Currency Real Return Analysis" in output
        assert "2023-03-31" in output
        assert "2026-01-31" in output
        assert "2.84 years" in output

    def test_contains_currencies(self) -> None:
        result = _make_result()
        output = format_table(result)
        assert "USD" in output
        assert "EUR" in output

    def test_contains_values(self) -> None:
        result = _make_result()
        output = format_table(result)
        assert "$10.00K" in output
        assert "$12.06K" in output

    def test_fx_dash_for_base(self) -> None:
        result = _make_result()
        output = format_table(result)
        # USD row should have — for FX
        assert "—" in output

    def test_warnings_shown(self) -> None:
        result = _make_result()
        output = format_table(result)
        assert "Test warning." in output

    def test_cagr_columns(self) -> None:
        result = _make_result(show_cagr=True)
        output = format_table(result, show_cagr=True)
        assert "Nom CAGR" in output

    def test_no_cagr_by_default(self) -> None:
        result = _make_result()
        output = format_table(result)
        assert "Nom CAGR" not in output


class TestFormatJson:
    def test_valid_json(self) -> None:
        result = _make_result()
        output = format_json(result)
        data = json.loads(output)
        assert data["base_currency"] == "USD"

    def test_period(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        assert data["period"]["start_date"] == "2023-03-31"
        assert data["period"]["years"] == 2.84

    def test_results_count(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        assert len(data["results"]) == 2

    def test_includes_discounted(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        assert "discounted_end_value" in data["results"][0]

    def test_includes_real_cagr(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        assert "real_cagr_pct" in data["results"][0]

    def test_cagr_adds_nominal(self) -> None:
        result = _make_result(show_cagr=True)
        data = json.loads(format_json(result, show_cagr=True))
        assert "nominal_cagr_pct" in data["results"][0]

    def test_warnings_in_json(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        assert "warnings" in data

    def test_no_warnings_when_empty(self) -> None:
        result = _make_result()
        result.warnings = []
        data = json.loads(format_json(result))
        assert "warnings" not in data

    def test_data_sources(self) -> None:
        result = _make_result()
        data = json.loads(format_json(result))
        assert data["data_sources"]["fx"] == "Frankfurter API"
        assert "US" in data["data_sources"]["cpi"]


class TestFormatCsv:
    def test_header_row(self) -> None:
        result = _make_result()
        output = format_csv(result)
        lines = output.strip().split("\n")
        assert "currency" in lines[0]
        assert "discounted_end_value" in lines[0]
        assert "real_cagr_pct" in lines[0]

    def test_data_rows(self) -> None:
        result = _make_result()
        output = format_csv(result)
        lines = output.strip().split("\n")
        assert len(lines) == 3  # header + 2 currencies

    def test_cagr_column(self) -> None:
        result = _make_result(show_cagr=True)
        output = format_csv(result, show_cagr=True)
        assert "nominal_cagr_pct" in output
