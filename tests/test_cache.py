"""Tests for cache module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcra import cache
from mcra.models import CPICacheEntry


class TestCpiCache:
    def test_save_and_load(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)

        entry = CPICacheEntry(
            country="US",
            source="FRED",
            last_updated=datetime.now(UTC),
            base_year="1982-84",
            series={"2023-01": 299.17, "2023-02": 300.84},
        )
        cache.save_cpi_cache(entry)

        loaded = cache.load_cpi_cache("US")
        assert loaded is not None
        assert loaded.country == "US"
        assert loaded.series["2023-01"] == 299.17

    def test_load_missing(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        assert cache.load_cpi_cache("XX") is None

    def test_load_corrupt(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        (tmp_path / "cpi_US.json").write_text("not json")
        assert cache.load_cpi_cache("US") is None

    def test_staleness(self) -> None:
        fresh = CPICacheEntry(
            country="US",
            source="FRED",
            last_updated=datetime.now(UTC),
            base_year="1982-84",
            series={},
        )
        assert not cache.is_cpi_stale(fresh)

        old = CPICacheEntry(
            country="US",
            source="FRED",
            last_updated=datetime.now(UTC) - timedelta(days=60),
            base_year="1982-84",
            series={},
        )
        assert cache.is_cpi_stale(old)


class TestFxCache:
    def test_save_and_load(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        monkeypatch.setattr("mcra.cache._FX_PATH", tmp_path / "fx_cache.json")

        cache.save_fx_rates("2023-03-31", "USD", {"EUR": 0.92, "GBP": 0.81})

        assert cache.load_fx_rate("2023-03-31", "USD", "EUR") == 0.92
        assert cache.load_fx_rate("2023-03-31", "USD", "GBP") == 0.81
        assert cache.load_fx_rate("2023-03-31", "USD", "CHF") is None

    def test_load_empty(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        monkeypatch.setattr("mcra.cache._FX_PATH", tmp_path / "fx_cache.json")
        assert cache.load_fx_rate("2023-03-31", "USD", "EUR") is None


class TestCacheManagement:
    def test_cache_status(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        (tmp_path / "test.json").write_text("{}")

        entries = cache.cache_status()
        assert len(entries) == 1
        assert entries[0]["file"] == "test.json"

    def test_cache_status_empty(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        assert cache.cache_status() == []

    def test_clear_cache(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path)
        (tmp_path / "a.json").write_text("{}")
        (tmp_path / "b.json").write_text("{}")

        count = cache.clear_cache()
        assert count == 2
        assert list(tmp_path.iterdir()) == []

    def test_clear_nonexistent(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("mcra.cache.CACHE_DIR", tmp_path / "nope")
        assert cache.clear_cache() == 0
