# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- `Makefile` with targets for all quality gates (`check`, `lint`, `typecheck`, `test`, `cov`), sample runs, cache management, and TUI launch (`tui`)
- Interactive terminal UI (`mcra-tui`) built with Textual — form inputs for dates, portfolio values, and currencies; `DataTable` for results; keyboard shortcut `Ctrl+R` to run
- `textual>=1.0` dependency
