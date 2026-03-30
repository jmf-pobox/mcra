.PHONY: install check fmt lint typecheck test cov run run-json run-csv run-cagr run-cache refresh-cache tui help

SRCS := mcra/ tests/

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install all deps (core + dev + coverage)
	uv sync --all-extras --all-groups

check: fmt lint typecheck test ## Run all quality gates

fmt: ## Check formatting (black)
	uv run black --check $(SRCS)

lint: ## Lint (ruff)
	uv run ruff check $(SRCS)

typecheck: ## Type check (mypy --strict)
	uv run mypy --strict mcra/

test: ## Run test suite
	uv run pytest tests/ -q

cov: ## Run tests with coverage report
	uv run pytest tests/ --cov=mcra --cov-report=term-missing -q

run: ## Run with sample inputs
	uv run mcra --start-date 2023-03-31 --start-value 10000 \
	     --end-date 2025-12-31 --end-value 12064

run-json: ## Run with JSON output
	uv run mcra --start-date 2023-03-31 --start-value 10000 \
	     --end-date 2025-12-31 --end-value 12064 --output json

run-csv: ## Run with CSV output
	uv run mcra --start-date 2023-03-31 --start-value 10000 \
	     --end-date 2025-12-31 --end-value 12064 --output csv

run-cagr: ## Run with CAGR column
	uv run mcra --start-date 2023-03-31 --start-value 10000 \
	     --end-date 2025-12-31 --end-value 12064 --cagr

run-cache: ## Show cache status
	uv run mcra --cache-status

refresh-cache: ## Force refresh cached CPI data
	uv run mcra --refresh-cache

tui: ## Launch the Textual TUI
	uv run mcra-tui
