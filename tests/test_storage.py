"""Tests for the Storage class and merge helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from binformer.storage import Storage, merge_deposits, merge_trades, merge_withdrawals

# ── Storage class ──────────────────────────────────────────────────────────────


class TestStorageRoot:
    def test_accepts_string_root(self, tmp_path: Path) -> None:
        s = Storage(str(tmp_path / "data"))
        assert s.root == tmp_path / "data"

    def test_accepts_path_root(self, tmp_path: Path) -> None:
        s = Storage(tmp_path / "data")
        assert s.root == tmp_path / "data"

    def test_default_root_is_user_data(self) -> None:
        assert Storage().root == Path("user_data")

    def test_separate_instances_are_independent(self, tmp_path: Path) -> None:
        a = Storage(tmp_path / "a")
        b = Storage(tmp_path / "b")
        a.save_metadata({"x": 1})
        assert b.load_metadata() == {}


class TestStorageTrades:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        assert s.load_trades("BTCUSDT") == []

    def test_roundtrip(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        trades = [{"id": "1", "time": "1000", "symbol": "BTCUSDT"}]
        s.save_trades("BTCUSDT", trades)
        assert s.load_trades("BTCUSDT") == trades

    def test_creates_trades_subdirectory(self, tmp_path: Path) -> None:
        s = Storage(tmp_path / "cache")
        s.save_trades("ETHUSDT", [])
        assert (tmp_path / "cache" / "trades").is_dir()

    def test_separate_symbols_stored_separately(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        s.save_trades("BTCUSDT", [{"id": "1", "time": "1"}])
        s.save_trades("ETHUSDT", [{"id": "2", "time": "2"}])
        assert s.load_trades("BTCUSDT")[0]["id"] == "1"
        assert s.load_trades("ETHUSDT")[0]["id"] == "2"


class TestStorageDeposits:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert Storage(tmp_path).load_deposits() == []

    def test_roundtrip_with_date(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        rows = [{"date": date(2026, 4, 6), "coin": "USDT", "amount": 100.0, "time_ms": 1000}]
        s.save_deposits(rows)
        loaded = s.load_deposits()
        assert len(loaded) == 1
        assert loaded[0]["date"] == date(2026, 4, 6)
        assert loaded[0]["coin"] == "USDT"


class TestStorageWithdrawals:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert Storage(tmp_path).load_withdrawals() == []

    def test_roundtrip_with_date(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        rows = [{"date": date(2026, 5, 1), "coin": "BTC", "amount": 0.01}]
        s.save_withdrawals(rows)
        loaded = s.load_withdrawals()
        assert loaded[0]["date"] == date(2026, 5, 1)


class TestStorageDailyBalances:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert Storage(tmp_path).load_daily_balances() == {}

    def test_roundtrip(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        d = date(2026, 4, 10)
        balances: dict[date, dict[str, float]] = {d: {"BTC": 0.5, "USDT": 100.0}}
        s.save_daily_balances(balances)
        loaded = s.load_daily_balances()
        assert loaded[d] == {"BTC": 0.5, "USDT": 100.0}

    def test_date_keys_roundtrip(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        dates = [date(2026, 4, i) for i in range(1, 4)]
        balances = {d: {"USDT": float(i * 10)} for i, d in enumerate(dates, 1)}
        s.save_daily_balances(balances)
        loaded = s.load_daily_balances()
        assert set(loaded.keys()) == set(dates)


class TestStorageMetadata:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert Storage(tmp_path).load_metadata() == {}

    def test_roundtrip(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        data = {"symbols": ["BTCUSDT"], "start_date": "2026-04-06"}
        s.save_metadata(data)
        assert s.load_metadata() == data

    def test_overwrite(self, tmp_path: Path) -> None:
        s = Storage(tmp_path)
        s.save_metadata({"v": 1})
        s.save_metadata({"v": 2})
        assert s.load_metadata()["v"] == 2


# ── Merge helpers ──────────────────────────────────────────────────────────────


class TestMergeTrades:
    def test_deduplicates_by_id(self) -> None:
        existing = [{"id": "1", "time": "100"}]
        fresh = [{"id": "1", "time": "100"}, {"id": "2", "time": "200"}]
        merged = merge_trades(existing, fresh)
        assert len(merged) == 2
        assert [t["id"] for t in merged] == ["1", "2"]

    def test_sorted_by_time(self) -> None:
        existing = [{"id": "2", "time": "200"}]
        fresh = [{"id": "1", "time": "100"}]
        merged = merge_trades(existing, fresh)
        assert [t["id"] for t in merged] == ["1", "2"]

    def test_empty_fresh(self) -> None:
        existing = [{"id": "1", "time": "100"}]
        assert merge_trades(existing, []) == existing


class TestMergeDeposits:
    def test_deduplicates_by_time_ms_and_coin(self) -> None:
        existing = [{"time_ms": 1000, "coin": "USDT", "amount": 50.0}]
        fresh = [
            {"time_ms": 1000, "coin": "USDT", "amount": 50.0},
            {"time_ms": 2000, "coin": "BTC", "amount": 0.01},
        ]
        merged = merge_deposits(existing, fresh)
        assert len(merged) == 2

    def test_same_time_different_coin_kept(self) -> None:
        existing = [{"time_ms": 1000, "coin": "USDT", "amount": 50.0}]
        fresh = [{"time_ms": 1000, "coin": "BTC", "amount": 0.01}]
        merged = merge_deposits(existing, fresh)
        assert len(merged) == 2


class TestMergeWithdrawals:
    def test_deduplicates_by_date_coin_amount(self) -> None:
        d = date(2026, 4, 10)
        existing = [{"date": d, "coin": "USDT", "amount": 100.0}]
        fresh = [
            {"date": d, "coin": "USDT", "amount": 100.0},
            {"date": d, "coin": "BTC", "amount": 0.01},
        ]
        merged = merge_withdrawals(existing, fresh)
        assert len(merged) == 2

    def test_empty_existing(self) -> None:
        fresh = [{"date": date(2026, 4, 1), "coin": "USDT", "amount": 50.0}]
        assert merge_withdrawals([], fresh) == fresh


# ── Custom data-dir isolation ──────────────────────────────────────────────────


class TestStorageIsolation:
    def test_two_dirs_do_not_share_data(self, tmp_path: Path) -> None:
        live = Storage(tmp_path / "live")
        test = Storage(tmp_path / "test")
        live.save_metadata({"env": "live"})
        test.save_metadata({"env": "test"})
        assert live.load_metadata()["env"] == "live"
        assert test.load_metadata()["env"] == "test"

    def test_storage_creates_nested_dirs(self, tmp_path: Path) -> None:
        s = Storage(tmp_path / "a" / "b" / "c")
        s.save_trades("BTCUSDT", [])
        assert (tmp_path / "a" / "b" / "c" / "trades").is_dir()

    @pytest.mark.parametrize("subdir", ["live_data", "test_data", "dry_run"])
    def test_parametric_roots(self, tmp_path: Path, subdir: str) -> None:
        s = Storage(tmp_path / subdir)
        s.save_metadata({"label": subdir})
        assert s.load_metadata()["label"] == subdir
