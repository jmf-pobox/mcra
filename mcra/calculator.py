"""Pure calculation functions for portfolio return analysis."""

from __future__ import annotations

from datetime import date


def years_between(start: date, end: date) -> float:
    """Fractional years between two dates."""
    return (end - start).days / 365.25


def convert_to_currency(value_base: float, fx_rate: float) -> float:
    """Convert a base-currency value using an FX rate (units of target per 1 base)."""
    return value_base * fx_rate


def nominal_return(start_value: float, end_value: float) -> float:
    """Total nominal return as a decimal (0.232 = 23.2%)."""
    return (end_value / start_value) - 1


def nominal_cagr(start_value: float, end_value: float, years: float) -> float:
    """Compound Annual Growth Rate."""
    if years <= 0:
        raise ValueError("Period must be positive")
    return float((end_value / start_value) ** (1 / years)) - 1


def cumulative_inflation(cpi_start: float, cpi_end: float) -> float:
    """Cumulative inflation as a decimal (0.074 = 7.4%)."""
    return (cpi_end / cpi_start) - 1


def annualized_inflation(cpi_start: float, cpi_end: float, years: float) -> float:
    """Annualized inflation rate."""
    if years <= 0:
        raise ValueError("Period must be positive")
    return float((cpi_end / cpi_start) ** (1 / years)) - 1


def real_return(nominal: float, inflation: float) -> float:
    """Real return via Fisher equation: (1 + r_real) = (1 + r_nom) / (1 + r_inf)."""
    return (1 + nominal) / (1 + inflation) - 1


def real_cagr(nominal_cagr_val: float, annualized_inf: float) -> float:
    """Real CAGR via Fisher equation applied to annualized rates."""
    return (1 + nominal_cagr_val) / (1 + annualized_inf) - 1


def discount_for_inflation(end_value: float, cumulative_infl: float) -> float:
    """Discount an end value back to start-date purchasing power."""
    return end_value / (1 + cumulative_infl)


def fx_change(fx_start: float, fx_end: float) -> float:
    """Percentage change in FX rate.

    Negative means base currency weakened vs target.
    """
    return (fx_end / fx_start) - 1
