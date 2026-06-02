# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
uv sync --all-extras --all-groups   # Install all deps (core + dev + coverage)
uv run pytest tests/ -q             # Run full test suite (104 tests)
uv run pytest tests/test_cpi.py -q  # Run a single test file
uv run pytest tests/ -k "test_nearest"  # Run tests matching a name pattern
uv run black --check mcra/ tests/   # Check formatting
uv run ruff check mcra/ tests/      # Lint
uv run mypy --strict mcra/          # Type check (strict mode required)
uv run mcra --help                  # Run the CLI
```

All four quality gates (black, ruff, mypy --strict, pytest) must pass before committing.

## Architecture

**Data flow:** CLI args → validation → async engine → parallel API fetches → per-currency calculations → formatted output.

The core pipeline in `cli.py:_run_analysis()`:

1. `asyncio.gather()` fetches FX rates (Frankfurter API) and CPI data (FRED/ONS/Eurostat) in parallel
2. For each target currency: FX-convert portfolio values, compute nominal/real returns via Fisher equation, discount for inflation
3. Results collected into `AnalysisResult` dataclass, passed to formatter

**Module responsibilities:**

- **cli.py** — Click entry point, validation, orchestration. Owns `_run_analysis()` (planned extraction to `engine.py`, see TODO.md)
- **calculator.py** — Pure functions: `nominal_return`, `real_return`, `cumulative_inflation`, `real_cagr`, `discount_for_inflation`. No I/O, no state
- **cpi.py** — Async CPI fetching with multi-level data resolution (see CPI Data Provenance below). CPI month lookup: exact match → linear interpolation → nearest month
- **fx.py** — Async Frankfurter API client. Cache-first, permanent cache (historical rates are immutable)
- **cache.py** — File-based JSON cache in `~/.mcra/cache/`. CPI staleness threshold: 30 days. FX cached permanently
- **formatters.py** — Table (Rich), JSON, CSV output. K/M/B suffix formatting for display values
- **models.py** — Dataclasses with `slots=True`, PEP 695 type aliases (`CPISeries`, `CountryCPIData`), currency registry

**Dependency direction:** `cli.py` → `{calculator, cpi, fx, formatters}` → `{models, cache}`. No circular imports.

## Key Patterns

**Async client injection:** All API modules accept `httpx.AsyncClient` as a parameter — never create clients internally. This enables the CLI to use short-lived clients and a future MCP server to reuse long-lived ones.

**Graceful degradation with warnings:** API failures don't crash the tool. The fallback chain (cache → stale cache → bundled CSV) produces results with warnings appended to `AnalysisResult.warnings`. Warnings surface in all output formats.

**Type aliases propagated:** Use `CPISeries` (not `dict[str, float]`) and `CountryCPIData` (not `dict[str, CPISeries]`) throughout `cpi.py` and `models.py`.

## CPI Data Provenance

Each CPI value has a provenance that is reported in warnings. The resolution order in `cpi.py:fetch_cpi_for_currency()`:

1. **Primary API** — fresh data from the authoritative source for each currency:
   - USD → FRED (series `CPIAUCNS`, BLS CPI-U, base 1982-84=100). Requires `FRED_API_KEY` env var.
   - GBP → ONS (series `D7BT`, UK CPI all items, base 2015=100). No API key.
   - EUR/CHF/JPY → Eurostat (dataset `prc_hicp_midx`, HICP, base 2015=100). No API key.
2. **Supplemental values** (`_SUPPLEMENTAL` dict in `cpi.py`) — authoritative values from alternative sources for months the primary API cannot serve. Applied at query time, never cached, replaced when the primary API publishes the month. Each entry documents its source. Current entries:
   - US 2025-10: Treasury TIPS contingency value (325.604). BLS could not publish due to government shutdown.
   - CH 2026-01 through 2026-04: BFS (Swiss Federal Statistical Office) national CPI values, scaled to Eurostat HICP using the December 2025 overlap (Eurostat 107.07 / BFS 107.9).
3. **Seasonal-trend composite estimation** (`fill_estimated_months()`) — for months still missing after steps 1–2. Geometric blend of (a) seasonal ratio: average month-over-month CPI change for that calendar month across the prior 3 years, and (b) trailing trend: geometric mean of the last 3 consecutive month-over-month ratios. Never cached — recomputed each run.
4. **Stale cache / bundled CSV** — last-resort fallback if the API fails entirely.

The API fetch window is widened by `SEASONAL_LOOKBACK_YEARS` (3) years before `start_date` to provide seasonal history for estimation.

A `_covers_analysis_window()` check ensures that API data reaching only into the distant past (e.g., Eurostat returning UK HICP only through 2020 post-Brexit) falls through to a better source.

## Testing Patterns

- **Cache isolation:** Tests monkeypatch `mcra.cache.CACHE_DIR` and `mcra.cache._FX_PATH` to `tmp_path`. The `test_fx.py` file uses an `autouse` fixture for this.
- **HTTP mocking:** `pytest-httpx` for API responses. No real network calls in tests.
- **Async tests:** `asyncio_mode = "auto"` in pytest config. Use `@pytest.mark.asyncio` and `async def test_...`.
- **CLI tests:** `click.testing.CliRunner` with `@patch("mcra.cli._run_analysis", new_callable=AsyncMock)` to mock the async engine.
- **Float comparison:** `pytest.approx(expected, rel=1e-3)` for all floating-point assertions.
- **Environment variables:** `monkeypatch.setenv("FRED_API_KEY", ...)` / `monkeypatch.delenv("FRED_API_KEY", raising=False)` for API key tests.

## Constraints

- Python 3.14+ required (PEP 649/749 deferred annotations, PEP 758 `except` without parens, PEP 695 `type` statements)
- `mypy --strict` enforced — all functions must have complete type annotations
- Ruff rules: `E, F, W, I, N, UP, B, A, SIM` — includes import sorting (I), pyupgrade (UP), bugbear (B)
- `@dataclass(slots=True)` on all dataclasses
- `zip(..., strict=True)` required by ruff B905
- Exception chaining: `raise ... from exc` required by ruff B904
