"""File-based caching for FX rates and CPI data.

Cache layout:
    ~/.mcra/cache/
        cpi_US.json
        cpi_DE.json
        fx_cache.json
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcra.models import CPICacheEntry

CACHE_DIR = Path.home() / ".mcra" / "cache"
CPI_STALENESS_DAYS = 30


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


# --- CPI cache ---

def _cpi_path(country: str) -> Path:
    return CACHE_DIR / f"cpi_{country}.json"


def load_cpi_cache(country: str) -> CPICacheEntry | None:
    path = _cpi_path(country)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return CPICacheEntry(
            country=data["country"],
            source=data["source"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
            base_year=data["base_year"],
            series=data["series"],
        )
    except (json.JSONDecodeError, KeyError):
        return None


def save_cpi_cache(entry: CPICacheEntry) -> None:
    _ensure_cache_dir()
    data = {
        "country": entry.country,
        "source": entry.source,
        "last_updated": entry.last_updated.isoformat(),
        "base_year": entry.base_year,
        "series": entry.series,
    }
    _cpi_path(entry.country).write_text(json.dumps(data, indent=2))


def is_cpi_stale(entry: CPICacheEntry) -> bool:
    age = datetime.now(timezone.utc) - entry.last_updated.replace(tzinfo=timezone.utc)
    return age > timedelta(days=CPI_STALENESS_DAYS)


# --- FX cache ---

_FX_PATH = CACHE_DIR / "fx_cache.json"


def _load_fx_store() -> dict:
    if not _FX_PATH.exists():
        return {}
    try:
        return json.loads(_FX_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def load_fx_rate(date_str: str, base: str, target: str) -> float | None:
    store = _load_fx_store()
    key = f"{date_str}:{base}:{target}"
    return store.get(key)


def save_fx_rates(date_str: str, base: str, rates: dict[str, float]) -> None:
    _ensure_cache_dir()
    store = _load_fx_store()
    for target, rate in rates.items():
        store[f"{date_str}:{base}:{target}"] = rate
    _FX_PATH.write_text(json.dumps(store, indent=2))


# --- Cache management ---

def cache_status() -> list[dict]:
    """Return info about each cache file for --cache-status."""
    _ensure_cache_dir()
    results = []
    for path in sorted(CACHE_DIR.iterdir()):
        if not path.is_file():
            continue
        stat = path.stat()
        results.append({
            "file": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return results


def clear_cache() -> int:
    """Delete all cache files. Returns count of files removed."""
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for path in CACHE_DIR.iterdir():
        if path.is_file():
            path.unlink()
            count += 1
    return count
