# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- ONS data source for UK CPI (series D7BT, 2015=100) — replaces Eurostat HICP which stopped reporting UK data post-Brexit
- Seasonal-trend composite CPI estimation for months not yet published by data sources — geometric blend of 3-year seasonal pattern and trailing 3-month trend, recomputed each run, never cached
- Supplemental CPI values from authoritative alternative sources (`_SUPPLEMENTAL` dict in `cpi.py`): US Oct 2025 via Treasury TIPS contingency (government shutdown), CH Jan–Apr 2026 via BFS national CPI scaled to Eurostat HICP
- API fetch window widened by 3 years before start date to provide seasonal history for estimation
- Coverage check (`_covers_analysis_window`) to prevent stale API data (e.g., Eurostat UK HICP ending 2020) from masking better fallback sources
- CPI Data Provenance section in CLAUDE.md documenting the full resolution chain
- 18 new tests for estimation, ONS fetcher, and month-key helpers (104 total)

### Changed
- Upgraded to Python 3.14+ — removed `from __future__ import annotations` (PEP 649/749), added `target-version` for black/ruff/mypy
- UK `cpi_source` changed from `"Eurostat"` to `"ONS"` in currency registry

### Previously added
- `Makefile` with targets for all quality gates (`check`, `lint`, `typecheck`, `test`, `cov`), sample runs, cache management, and TUI launch (`tui`)
- Interactive terminal UI (`mcra-tui`) built with Textual — form inputs for dates, portfolio values, and currencies; `DataTable` for results; keyboard shortcut `Ctrl+R` to run
- `textual>=1.0` dependency
