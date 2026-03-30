"""Textual TUI for MCRA."""

from __future__ import annotations

import logging
from datetime import date

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
)
from textual.worker import Worker, WorkerState

from mcra.cli import _run_analysis
from mcra.formatters import fmt_currency_value, fmt_pct
from mcra.models import CURRENCY_COUNTRY_MAP, SUPPORTED_CURRENCIES, AnalysisResult

_log = logging.getLogger(__name__)


class McraApp(App[None]):
    """Multi-Currency Real Return Analyzer."""

    CSS = """
    #form {
        dock: top;
        height: auto;
        padding: 1 2;
    }
    .form-row {
        height: 3;
        margin-bottom: 1;
    }
    .form-row Label {
        width: 18;
        content-align: right middle;
        padding-right: 1;
    }
    .form-row Input {
        width: 1fr;
    }
    #buttons {
        height: 3;
        margin-top: 1;
        align: center middle;
    }
    #buttons Button {
        margin: 0 1;
    }
    #results {
        height: 1fr;
        padding: 1 2;
    }
    #warnings {
        dock: bottom;
        height: auto;
        max-height: 6;
        padding: 0 2;
        color: $warning;
    }
    #status {
        dock: bottom;
        height: 1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("ctrl+r", "run_analysis", "Run"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            with Horizontal(classes="form-row"):
                yield Label("Start Date:")
                yield Input(
                    value="2023-03-31", id="start-date", placeholder="YYYY-MM-DD"
                )
                yield Label("End Date:")
                yield Input(value="2025-12-31", id="end-date", placeholder="YYYY-MM-DD")
            with Horizontal(classes="form-row"):
                yield Label("Start Value:")
                yield Input(value="10000", id="start-value", placeholder="e.g. 10000")
                yield Label("End Value:")
                yield Input(value="12064", id="end-value", placeholder="e.g. 12064")
            with Horizontal(classes="form-row"):
                yield Label("Base Currency:")
                yield Input(value="USD", id="base-currency", placeholder="e.g. USD")
                yield Label("Currencies:")
                yield Input(
                    value=",".join(SUPPORTED_CURRENCIES),
                    id="currencies",
                    placeholder="e.g. USD,EUR,GBP",
                )
            with Horizontal(id="buttons"):
                yield Button("Run Analysis", variant="primary", id="run-btn")
                yield Button("Clear", variant="default", id="clear-btn")
        yield DataTable(id="results")
        yield Static("", id="warnings")
        yield Static("Press Ctrl+R or click Run Analysis", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(
            "Currency",
            "Start Value",
            "End Value",
            "Disc. Value",
            "Nominal",
            "Real",
            "Real CAGR",
            "FX Δ",
            "Inflation",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.action_run_analysis()
        elif event.button.id == "clear-btn":
            table = self.query_one(DataTable)
            table.clear()
            self.query_one("#warnings", Static).update("")
            self.query_one("#status", Static).update("Cleared.")

    def action_run_analysis(self) -> None:
        self._do_analysis()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.ERROR:
            _log.exception("Worker error", exc_info=event.worker.error)
            self.query_one("#status", Static).update(
                f"Worker error: {event.worker.error}. See logs for details."
            )

    @work(exclusive=True)
    async def _do_analysis(self) -> None:
        status = self.query_one("#status", Static)
        warnings_widget = self.query_one("#warnings", Static)
        table = self.query_one(DataTable)

        warnings_widget.update("")
        table.clear()

        # Parse inputs
        try:
            start_date = date.fromisoformat(
                self.query_one("#start-date", Input).value.strip()
            )
        except ValueError:
            status.update("Start Date must be in YYYY-MM-DD format.")
            return

        try:
            end_date = date.fromisoformat(
                self.query_one("#end-date", Input).value.strip()
            )
        except ValueError:
            status.update("End Date must be in YYYY-MM-DD format.")
            return

        try:
            start_value = float(self.query_one("#start-value", Input).value.strip())
        except ValueError:
            status.update("Start Value must be a number.")
            return

        try:
            end_value = float(self.query_one("#end-value", Input).value.strip())
        except ValueError:
            status.update("End Value must be a number.")
            return

        base_currency = self.query_one("#base-currency", Input).value.strip().upper()
        currencies = [
            c.strip().upper()
            for c in self.query_one("#currencies", Input).value.split(",")
            if c.strip()
        ]

        # Validate
        if start_value <= 0:
            status.update("Start Value must be positive.")
            return
        if end_value <= 0:
            status.update("End Value must be positive.")
            return
        if end_date > date.today():
            status.update("End Date cannot be in the future.")
            return
        if end_date <= start_date:
            status.update("End Date must be after Start Date.")
            return
        if base_currency not in CURRENCY_COUNTRY_MAP:
            status.update(f"Unsupported base currency: {base_currency!r}.")
            return
        if not currencies:
            status.update("Enter at least one currency (e.g. USD,EUR,GBP).")
            return
        for c in currencies:
            if c not in CURRENCY_COUNTRY_MAP:
                status.update(f"Unsupported currency: {c!r}.")
                return

        if base_currency not in currencies:
            currencies.insert(0, base_currency)

        status.update("Fetching data...")

        try:
            result: AnalysisResult = await _run_analysis(
                start_date=start_date,
                end_date=end_date,
                start_value=start_value,
                end_value=end_value,
                base_currency=base_currency,
                currencies=currencies,
                show_cagr=False,
                force_refresh=False,
            )
        except httpx.TimeoutException:
            status.update("Request timed out. Check your network connection.")
            return
        except httpx.HTTPStatusError as exc:
            status.update(
                f"API error {exc.response.status_code} from "
                f"{exc.request.url.host}. Try again later."
            )
            return
        except httpx.RequestError as exc:
            status.update(f"Network error: {exc}.")
            return
        except KeyError as exc:
            status.update(f"Missing data for currency {exc}.")
            return
        except ValueError as exc:
            status.update(f"Data error: {exc}")
            return
        except Exception as exc:
            _log.exception("Unexpected error in _do_analysis")
            status.update(
                f"Unexpected error: {type(exc).__name__}: {exc}. "
                "Please report this as a bug."
            )
            return

        try:
            for r in result.results:
                fx_str = (
                    "—" if r.currency == base_currency else fmt_pct(r.fx_change_pct)
                )
                table.add_row(
                    r.currency,
                    fmt_currency_value(r.start_value, r.currency),
                    fmt_currency_value(r.end_value, r.currency),
                    fmt_currency_value(r.discounted_end_value, r.currency),
                    fmt_pct(r.nominal_return_pct),
                    fmt_pct(r.real_return_pct),
                    fmt_pct(r.real_cagr_pct),
                    fx_str,
                    fmt_pct(r.cumulative_inflation_pct, plus_sign=False),
                )
        except Exception as exc:
            _log.exception("Error rendering results")
            status.update(f"Error rendering results: {exc}")
            return

        p = result.period
        status.update(
            f"Period: {p.start_date} → {p.end_date} ({p.years:.2f} years) | "
            f"Base: {result.base_currency}"
        )

        if result.warnings:
            warnings_widget.update("\n".join(f"⚠ {w}" for w in result.warnings))


def main() -> None:
    """Launch the MCRA TUI."""
    app = McraApp()
    app.title = "MCRA — Multi-Currency Real Return Analyzer"
    app.run()


if __name__ == "__main__":
    main()
