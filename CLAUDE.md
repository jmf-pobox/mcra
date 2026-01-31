# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
uv sync --all-extras --all-groups   # Install all deps (core + dev + coverage)
uv run pytest tests/ -q             # Run full test suite (86 tests)
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

1. `asyncio.gather()` fetches FX rates (Frankfurter API) and CPI data (FRED/Eurostat) in parallel
2. For each target currency: FX-convert portfolio values, compute nominal/real returns via Fisher equation, discount for inflation
3. Results collected into `AnalysisResult` dataclass, passed to formatter

**Module responsibilities:**

- **cli.py** — Click entry point, validation, orchestration. Owns `_run_analysis()` (planned extraction to `engine.py`, see TODO.md)
- **calculator.py** — Pure functions: `nominal_return`, `real_return`, `cumulative_inflation`, `real_cagr`, `discount_for_inflation`. No I/O, no state
- **cpi.py** — Async CPI fetching with 5-level fallback: fresh cache → API (FRED for US, Eurostat for others) → stale cache → bundled CSV → error. CPI month lookup: exact match → linear interpolation → nearest month
- **fx.py** — Async Frankfurter API client. Cache-first, permanent cache (historical rates are immutable)
- **cache.py** — File-based JSON cache in `~/.mcra/cache/`. CPI staleness threshold: 30 days. FX cached permanently
- **formatters.py** — Table (Rich), JSON, CSV output. K/M/B suffix formatting for display values
- **models.py** — Dataclasses with `slots=True`, PEP 695 type aliases (`CPISeries`, `CountryCPIData`), currency registry

**Dependency direction:** `cli.py` → `{calculator, cpi, fx, formatters}` → `{models, cache}`. No circular imports.

## Key Patterns

**Async client injection:** All API modules accept `httpx.AsyncClient` as a parameter — never create clients internally. This enables the CLI to use short-lived clients and a future MCP server to reuse long-lived ones.

**Graceful degradation with warnings:** API failures don't crash the tool. The fallback chain (cache → stale cache → bundled CSV) produces results with warnings appended to `AnalysisResult.warnings`. Warnings surface in all output formats.

**Type aliases propagated:** Use `CPISeries` (not `dict[str, float]`) and `CountryCPIData` (not `dict[str, CPISeries]`) throughout `cpi.py` and `models.py`.

## Testing Patterns

- **Cache isolation:** Tests monkeypatch `mcra.cache.CACHE_DIR` and `mcra.cache._FX_PATH` to `tmp_path`. The `test_fx.py` file uses an `autouse` fixture for this.
- **HTTP mocking:** `pytest-httpx` for API responses. No real network calls in tests.
- **Async tests:** `asyncio_mode = "auto"` in pytest config. Use `@pytest.mark.asyncio` and `async def test_...`.
- **CLI tests:** `click.testing.CliRunner` with `@patch("mcra.cli._run_analysis", new_callable=AsyncMock)` to mock the async engine.
- **Float comparison:** `pytest.approx(expected, rel=1e-3)` for all floating-point assertions.
- **Environment variables:** `monkeypatch.setenv("FRED_API_KEY", ...)` / `monkeypatch.delenv("FRED_API_KEY", raising=False)` for API key tests.

## Constraints

- Python 3.12+ required (PEP 695 `type` statements, `datetime.UTC`)
- `mypy --strict` enforced — all functions must have complete type annotations
- Ruff rules: `E, F, W, I, N, UP, B, A, SIM` — includes import sorting (I), pyupgrade (UP), bugbear (B)
- `@dataclass(slots=True)` on all dataclasses
- `zip(..., strict=True)` required by ruff B905
- Exception chaining: `raise ... from exc` required by ruff B904
