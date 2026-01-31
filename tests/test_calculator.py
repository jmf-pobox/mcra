"""Tests for pure calculation functions."""

from datetime import date

import pytest

from mcra.calculator import (
    annualized_inflation,
    convert_to_currency,
    cumulative_inflation,
    fx_change,
    nominal_cagr,
    nominal_return,
    real_cagr,
    real_return,
    years_between,
)


class TestYearsBetween:
    def test_spec_example(self):
        start = date(2023, 3, 31)
        end = date(2026, 1, 28)
        assert years_between(start, end) == pytest.approx(2.83, rel=1e-2)

    def test_exact_one_year(self):
        result = years_between(date(2023, 1, 1), date(2024, 1, 1))
        assert result == pytest.approx(1.0, abs=0.01)

    def test_same_date(self):
        assert years_between(date(2023, 1, 1), date(2023, 1, 1)) == 0.0


class TestNominalReturn:
    def test_basic(self):
        # $1000 -> $1200 = 20% return
        assert nominal_return(1000.0, 1200.0) == pytest.approx(0.20, rel=1e-3)

    def test_no_change(self):
        assert nominal_return(100.0, 100.0) == 0.0

    def test_loss(self):
        assert nominal_return(100.0, 80.0) == pytest.approx(-0.20, rel=1e-3)


class TestNominalCAGR:
    def test_basic(self):
        # $100 to $121 in 2 years = 10% CAGR
        assert nominal_cagr(100.0, 121.0, 2.0) == pytest.approx(0.10, rel=1e-2)

    def test_zero_period_raises(self):
        with pytest.raises(ValueError):
            nominal_cagr(100.0, 110.0, 0.0)


class TestRealReturn:
    def test_spec_example(self):
        # 23.2% nominal, 7.4% inflation → ~14.7% real (Fisher equation)
        assert real_return(0.232, 0.074) == pytest.approx(0.147, rel=1e-2)

    def test_zero_inflation(self):
        assert real_return(0.10, 0.0) == pytest.approx(0.10, rel=1e-6)

    def test_inflation_equals_nominal(self):
        assert real_return(0.05, 0.05) == pytest.approx(0.0, abs=1e-6)


class TestRealCAGR:
    def test_fisher_applied_to_annualized(self):
        # 8% nominal CAGR, 3% annualized inflation
        result = real_cagr(0.08, 0.03)
        expected = (1.08 / 1.03) - 1
        assert result == pytest.approx(expected, rel=1e-6)


class TestCumulativeInflation:
    def test_basic(self):
        assert cumulative_inflation(100.0, 107.4) == pytest.approx(0.074, rel=1e-3)


class TestAnnualizedInflation:
    def test_basic(self):
        # CPI went from 100 to 110 over 2 years
        result = annualized_inflation(100.0, 110.0, 2.0)
        expected = (110.0 / 100.0) ** (1 / 2.0) - 1
        assert result == pytest.approx(expected, rel=1e-6)


class TestFxChange:
    def test_spec_example(self):
        # USD/EUR went from 0.920 to 0.833 = -9.5%
        assert fx_change(0.920, 0.833) == pytest.approx(-0.0946, rel=1e-2)

    def test_no_change(self):
        assert fx_change(1.0, 1.0) == 0.0


class TestConvertToCurrency:
    def test_basic(self):
        assert convert_to_currency(100.0, 0.92) == pytest.approx(92.0, rel=1e-6)

    def test_identity(self):
        assert convert_to_currency(1000.0, 1.0) == 1000.0
