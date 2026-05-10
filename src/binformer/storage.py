"""Persistent local cache: trades, deposits, withdrawals, reconstructed daily balances."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

# ── Pure merge helpers (stateless, no I/O) ─────────────────────────────────────


def merge_trades(
    existing: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {t["id"] for t in existing}
    merged = existing + [t for t in fresh if t["id"] not in seen]
    merged.sort(key=lambda t: int(t["time"]))
    return merged


def merge_deposits(
    existing: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {(r["time_ms"], r["coin"]) for r in existing}
    merged = existing + [r for r in fresh if (r["time_ms"], r["coin"]) not in seen]
    merged.sort(key=lambda r: r.get("time_ms", 0))
    return merged


def merge_withdrawals(
    existing: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {(str(r["date"]), r["coin"], r["amount"]) for r in existing}
    merged = existing + [
        r for r in fresh if (str(r["date"]), r["coin"], r["amount"]) not in seen
    ]
    merged.sort(key=lambda r: str(r.get("date", "")))
    return merged


# ── Storage class ──────────────────────────────────────────────────────────────


class Storage:
    """File-backed cache for Binance data, rooted at a configurable directory."""

    def __init__(self, root: Path | str = "user_data") -> None:
        self.root = Path(root)

    @property
    def _trades_dir(self) -> Path:
        return self.root / "trades"

    def _mkdir(self) -> None:
        self._trades_dir.mkdir(parents=True, exist_ok=True)

    # ── Trades ─────────────────────────────────────────────────────────────────

    def load_trades(self, symbol: str) -> list[dict[str, Any]]:
        p = self._trades_dir / f"{symbol}.json"
        return json.loads(p.read_text()) if p.exists() else []

    def save_trades(self, symbol: str, trades: list[dict[str, Any]]) -> None:
        self._mkdir()
        (self._trades_dir / f"{symbol}.json").write_text(json.dumps(trades))

    # ── Deposits ───────────────────────────────────────────────────────────────

    def _load_rows(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = json.loads(path.read_text())
        for r in rows:
            if isinstance(r.get("date"), str):
                r["date"] = date.fromisoformat(r["date"])
        return rows

    def _save_rows(self, path: Path, rows: list[dict[str, Any]]) -> None:
        self._mkdir()
        serialized = [{**r, "date": str(r["date"])} for r in rows]
        path.write_text(json.dumps(serialized))

    def load_deposits(self) -> list[dict[str, Any]]:
        return self._load_rows(self.root / "deposits.json")

    def save_deposits(self, rows: list[dict[str, Any]]) -> None:
        self._save_rows(self.root / "deposits.json", rows)

    def load_withdrawals(self) -> list[dict[str, Any]]:
        return self._load_rows(self.root / "withdrawals.json")

    def save_withdrawals(self, rows: list[dict[str, Any]]) -> None:
        self._save_rows(self.root / "withdrawals.json", rows)

    # ── Reconstructed daily balances ───────────────────────────────────────────

    def load_daily_balances(self) -> dict[date, dict[str, float]]:
        p = self.root / "balances.json"
        if not p.exists():
            return {}
        return {date.fromisoformat(k): v for k, v in json.loads(p.read_text()).items()}

    def save_daily_balances(self, balances: dict[date, dict[str, float]]) -> None:
        self._mkdir()
        serialized = {str(d): coins for d, coins in sorted(balances.items())}
        (self.root / "balances.json").write_text(json.dumps(serialized, indent=2))

    # ── Metadata ───────────────────────────────────────────────────────────────

    def load_metadata(self) -> dict[str, Any]:
        p = self.root / "metadata.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def save_metadata(self, data: dict[str, Any]) -> None:
        self._mkdir()
        (self.root / "metadata.json").write_text(json.dumps(data, indent=2))
