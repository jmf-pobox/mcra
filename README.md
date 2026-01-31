# mcra — Multi-Currency Real Return Analyzer

A Python CLI that calculates portfolio returns from multiple currency perspectives, adjusted for local inflation to produce real (purchasing-power-adjusted) returns.

Given a $10,000 portfolio that grew to $12,064 over ~2.8 years, the tool shows how that same investment performed when measured in EUR, GBP, CHF, etc., after adjusting for each country's inflation using the Fisher equation.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

```bash
# Basic usage
mcra --start-date 2023-03-31 --start-value 10000 --end-date 2026-01-31 --end-value 12064

# Specify currencies
mcra --start-date 2023-03-31 --start-value 10000 \
     --end-date 2026-01-31 --end-value 12064 \
     --currencies USD,EUR,GBP,CHF

# Include nominal CAGR column
mcra --start-date 2023-03-31 --start-value 10000 \
     --end-date 2026-01-31 --end-value 12064 --cagr

# JSON output
mcra --start-date 2023-03-31 --start-value 10000 \
     --end-date 2026-01-31 --end-value 12064 --output json

# CSV output
mcra --start-date 2023-03-31 --start-value 10000 \
     --end-date 2026-01-31 --end-value 12064 --output csv

# Cache management
mcra --cache-status
mcra --refresh-cache
```

### Example Output

```
Multi-Currency Real Return Analysis
===================================
Period: 2023-03-31 → 2026-01-31 (2.84 years)
Base currency: USD

 Currency   Start Value   End Value   Disc. Value   Nominal     Real   Real CAGR     FX Δ   Inflation
 USD            $10.00K     $12.06K       $11.24K    +20.6%   +12.4%       +4.2%        —        7.4%
 EUR             €9.20K     €10.12K        €9.53K    +10.1%    +3.7%       +1.3%    -8.8%        6.2%
 GBP             £8.08K      £8.77K        £8.27K     +8.4%    +2.3%       +0.8%   -10.1%        6.0%
 CHF          CHF 9.17K   CHF 9.27K     CHF 9.14K     +1.1%    -0.3%       -0.1%   -16.2%        1.5%
```

**Disc. Value** is the end value discounted back to start-date purchasing power. Compare it directly to Start Value to see real gain/loss.

Values display with K (thousands) or M (millions) suffixes automatically, keeping at most 3 digits left of the decimal.

## CLI Reference

```
REQUIRED:
    --start-date DATE       Start date (YYYY-MM-DD)
    --end-date DATE         End date (YYYY-MM-DD)
    --start-value FLOAT     Portfolio value at start
    --end-value FLOAT       Portfolio value at end

OPTIONAL:
    --base-currency CODE    Base currency of portfolio values (default: USD)
    --currencies LIST       Comma-separated target currencies (default: USD,EUR,GBP,CHF)
    --cagr                  Include nominal CAGR column
    --output FORMAT         table (default), json, csv
    --cache-status          Show cache file locations and freshness
    --refresh-cache         Force refresh of cached CPI data
    --help                  Show help
```

### Supported Currencies

| Code | Country       | CPI Source |
|------|---------------|------------|
| USD  | United States | FRED       |
| EUR  | Germany (Eurozone proxy) | Eurostat |
| GBP  | United Kingdom | Eurostat  |
| CHF  | Switzerland   | Eurostat   |
| JPY  | Japan         | Eurostat   |

## Data Sources

- **FX rates**: [Frankfurter API](https://frankfurter.dev) — free, no key required
- **US CPI**: [FRED](https://fred.stlouisfed.org/) series `CPIAUCNS` — requires `FRED_API_KEY` environment variable
- **Non-US CPI**: [Eurostat](https://ec.europa.eu/eurostat) HICP dataset `prc_hicp_midx` — free, no key required
- **Fallback**: Bundled CSV with monthly CPI indices (2022–2026)

### FRED API Key

For fresh US CPI data, set the `FRED_API_KEY` environment variable:

```bash
export FRED_API_KEY=your_key_here
```

Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html

Without it, the tool falls back to bundled/cached data with a warning.

## Calculations

| Metric | Formula |
|--------|---------|
| Nominal return | `(end / start) - 1` |
| Cumulative inflation | `(CPI_end / CPI_start) - 1` |
| Real return | `((1 + nominal) / (1 + inflation)) - 1` (Fisher equation) |
| Discounted value | `end_value / (1 + inflation)` |
| CAGR | `(end / start) ^ (1/years) - 1` |
| FX change | `(fx_end / fx_start) - 1` |

## Caching

Data is cached in `~/.mcra/cache/`:

- **CPI data**: Refreshed if older than 30 days
- **FX rates**: Cached indefinitely (historical rates don't change)
- Stale cache is used as fallback when APIs are unavailable

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Run without installing
uv run python -m mcra.cli --help
```

## Project Structure

```
mcra/
├── cli.py              # Click CLI entry point
├── calculator.py       # Pure calculation functions
├── fx.py               # Frankfurter API client (async)
├── cpi.py              # CPI fetching: FRED, Eurostat, CSV fallback
├── cache.py            # File-based cache (~/.mcra/cache/)
├── models.py           # Dataclasses for results and config
├── formatters.py       # Table (Rich), JSON, CSV output
└── data/
    └── cpi_fallback.csv  # Bundled CPI indices
```
