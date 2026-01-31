"""Tests for CLI entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from mcra.cli import main
from mcra.models import AnalysisPeriod, AnalysisResult, CurrencyResult


def _mock_result() -> AnalysisResult:
    from datetime import date

    return AnalysisResult(
        period=AnalysisPeriod(
            start_date=date(2023, 3, 31),
            end_date=date(2024, 3, 31),
            years=1.0,
        ),
        base_currency="USD",
        start_value=10000.0,
        end_value=11000.0,
        results=[
            CurrencyResult(
                currency="USD",
                country="US",
                start_value=10000.0,
                end_value=11000.0,
                fx_rate_start=1.0,
                fx_rate_end=1.0,
                fx_change_pct=0.0,
                nominal_return_pct=0.10,
                cumulative_inflation_pct=0.03,
                real_return_pct=0.068,
                discounted_end_value=10679.61,
                real_cagr_pct=0.068,
                nominal_cagr_pct=None,
            ),
        ],
    )


class TestCliValidation:
    def test_missing_required(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--start-date", "2023-03-31"])
        assert result.exit_code != 0
        assert "Missing required" in result.output

    def test_invalid_date(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "not-a-date",
                "--end-date",
                "2024-01-01",
                "--start-value",
                "100",
                "--end-value",
                "110",
            ],
        )
        assert result.exit_code != 0

    def test_end_before_start(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2023-01-01",
                "--start-value",
                "100",
                "--end-value",
                "110",
            ],
        )
        assert result.exit_code != 0
        assert "End date must be after start date" in result.output

    def test_zero_start_value(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "2023-01-01",
                "--end-date",
                "2024-01-01",
                "--start-value",
                "0",
                "--end-value",
                "110",
            ],
        )
        assert result.exit_code != 0
        assert "must be positive" in result.output

    def test_unsupported_currency(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "2023-01-01",
                "--end-date",
                "2024-01-01",
                "--start-value",
                "100",
                "--end-value",
                "110",
                "--currencies",
                "XYZ",
            ],
        )
        assert result.exit_code != 0

    def test_unsupported_base_currency(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "2023-01-01",
                "--end-date",
                "2024-01-01",
                "--start-value",
                "100",
                "--end-value",
                "110",
                "--base-currency",
                "XYZ",
            ],
        )
        assert result.exit_code != 0
        assert "not supported" in result.output


class TestCliOutput:
    @patch("mcra.cli._run_analysis", new_callable=AsyncMock)
    def test_table_output(self, mock_analysis: AsyncMock) -> None:
        mock_analysis.return_value = _mock_result()
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "2023-03-31",
                "--end-date",
                "2024-03-31",
                "--start-value",
                "10000",
                "--end-value",
                "11000",
                "--currencies",
                "USD",
            ],
        )
        assert result.exit_code == 0
        assert "Multi-Currency Real Return Analysis" in result.output

    @patch("mcra.cli._run_analysis", new_callable=AsyncMock)
    def test_json_output(self, mock_analysis: AsyncMock) -> None:
        mock_analysis.return_value = _mock_result()
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "2023-03-31",
                "--end-date",
                "2024-03-31",
                "--start-value",
                "10000",
                "--end-value",
                "11000",
                "--currencies",
                "USD",
                "--output",
                "json",
            ],
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data["base_currency"] == "USD"

    @patch("mcra.cli._run_analysis", new_callable=AsyncMock)
    def test_csv_output(self, mock_analysis: AsyncMock) -> None:
        mock_analysis.return_value = _mock_result()
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--start-date",
                "2023-03-31",
                "--end-date",
                "2024-03-31",
                "--start-value",
                "10000",
                "--end-value",
                "11000",
                "--currencies",
                "USD",
                "--output",
                "csv",
            ],
        )
        assert result.exit_code == 0
        assert "currency,country" in result.output


class TestCliCacheCommands:
    def test_cache_status(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["--cache-status"])
        assert result.exit_code == 0

    def test_refresh_cache(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        (tmp_path / "test.json").write_text("{}")
        runner = CliRunner()
        result = runner.invoke(main, ["--refresh-cache"])
        assert result.exit_code == 0
        assert "Cleared" in result.output

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Multi-Currency Real Return Analyzer" in result.output
