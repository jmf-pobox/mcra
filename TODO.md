# MCP Server Addition

Expose the MCRA CLI as an MCP (Model Context Protocol) server, enabling LLMs to invoke portfolio return analysis as a tool.

Single-user MCP server model assumed throughout.

---

## 1. Extract analysis engine from cli.py

**File:** `mcra/engine.py` (new)

Move `_run_analysis` from `cli.py` into a public `run_analysis()` function. Accept `httpx.AsyncClient` as a parameter instead of creating one internally — the CLI creates a short-lived client per invocation, the MCP server reuses a long-lived client.

```python
async def run_analysis(
    client: httpx.AsyncClient,
    start_date: date,
    end_date: date,
    start_value: float,
    end_value: float,
    base_currency: str,
    currencies: list[str],
    show_cagr: bool = False,
    force_refresh: bool = False,
) -> AnalysisResult:
```

`cli.py` becomes a thin adapter: parse args, create client, call `run_analysis`, format output.

## 2. Extract validation from Click

**File:** `mcra/engine.py`

Move input validation (date ordering, positive values, supported currencies, future date check) out of `cli.py:main()` into a framework-agnostic function that raises `MCRAValidationError`. Both CLI and MCP handlers catch and translate to their respective error formats.

```python
def validate_inputs(
    start_date: date,
    end_date: date,
    start_value: float,
    end_value: float,
    base_currency: str,
    currencies: list[str],
) -> list[str]:
    """Validate inputs. Returns validated currency list. Raises MCRAValidationError on failure."""
```

## 3. Custom exception types

**File:** `mcra/errors.py` (new)

```python
class MCRAError(Exception): ...
class MCRAValidationError(MCRAError): ...  # bad input
class MCRADataError(MCRAError): ...        # API/data failure
```

Replace bare `ValueError` in `cpi.py:268`, `calculator.py:26,37` and `OSError` in `cpi.py:37` with these. The MCP handler maps `MCRAValidationError` to `isError: true` with a user-facing message, and `MCRADataError` to a retry-suggesting message.

## 4. Add `to_dict()` serialization to AnalysisResult

**File:** `mcra/models.py`

Add a `to_dict()` method on `AnalysisResult` that returns raw numeric values (no rounding, no percentage multiplication, no conditional field inclusion). The MCP server returns this directly; the LLM formats for the user. `format_json` in `formatters.py` continues to serve the CLI with its display-oriented formatting.

## 5. Add MCP server module

**File:** `mcra/server.py` (new)

Define one tool: `analyze_returns`. Input schema derived from `run_analysis` parameters. The handler:

1. Calls `validate_inputs`
2. Calls `run_analysis` with a shared `httpx.AsyncClient`
3. Returns `result.to_dict()` on success
4. Returns `isError: true` with message on `MCRAError`

Add entry point in `pyproject.toml`:

```toml
[project.scripts]
mcra = "mcra.cli:main"
mcra-mcp = "mcra.server:main"
```

## 6. Add `mcp` dependency

**File:** `pyproject.toml`

Add `mcp` to `[project.dependencies]`. Move `click` and `rich` to `[project.optional-dependencies] cli = [...]` so the MCP server doesn't pull in CLI-only packages.

```toml
dependencies = [
    "httpx>=0.27",
    "mcp>=1.0",
]

[project.optional-dependencies]
cli = [
    "click>=8.0",
    "rich>=13.0",
]
```

---

## Unchanged modules

- **calculator.py** — Pure functions, no changes.
- **cpi.py** — Already async, already accepts injected client. Only change: use `MCRADataError` instead of `ValueError`/`OSError`.
- **fx.py** — Same as cpi.py.
- **cache.py** — File-based caching works as-is for single-user MCP.
- **formatters.py** — CLI-only output. No changes.

## Implementation order

1. `mcra/errors.py` — exception types (no existing code depends on it yet)
2. `mcra/engine.py` — extract engine + validation from `cli.py`
3. Update `cli.py` — thin adapter calling `engine.run_analysis`
4. `AnalysisResult.to_dict()` — serialization method
5. Replace bare exceptions in `cpi.py`, `calculator.py` with custom types
6. `mcra/server.py` — MCP tool definition and handler
7. `pyproject.toml` — dependency and entry point changes
8. Tests for MCP server
