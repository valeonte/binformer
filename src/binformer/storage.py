"""Persistent local cache: trades, deposits, withdrawals, reconstructed daily balances."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

_ROOT = Path("user_data")
_TRADES = _ROOT / "trades"


def _mkdir() -> None:
    _TRADES.mkdir(parents=True, exist_ok=True)


# ── Trades ─────────────────────────────────────────────────────────────────

def load_trades(symbol: str) -> list[dict[str, Any]]:
    p = _TRADES / f"{symbol}.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_trades(symbol: str, trades: list[dict[str, Any]]) -> None:
    _mkdir()
    (_TRADES / f"{symbol}.json").write_text(json.dumps(trades))


def merge_trades(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {t["id"] for t in existing}
    merged = existing + [t for t in fresh if t["id"] not in seen]
    merged.sort(key=lambda t: int(t["time"]))
    return merged


# ── Deposits ───────────────────────────────────────────────────────────────

def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = json.loads(path.read_text())
    for r in rows:
        if isinstance(r.get("date"), str):
            r["date"] = date.fromisoformat(r["date"])
    return rows


def _save_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    _mkdir()
    path.write_text(json.dumps([{**r, "date": str(r["date"])} for r in rows]))


def load_deposits() -> list[dict[str, Any]]:
    return _load_rows(_ROOT / "deposits.json")


def save_deposits(rows: list[dict[str, Any]]) -> None:
    _save_rows(_ROOT / "deposits.json", rows)


def merge_deposits(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {(r["time_ms"], r["coin"]) for r in existing}
    merged = existing + [r for r in fresh if (r["time_ms"], r["coin"]) not in seen]
    merged.sort(key=lambda r: r.get("time_ms", 0))
    return merged


# ── Withdrawals ────────────────────────────────────────────────────────────

def load_withdrawals() -> list[dict[str, Any]]:
    return _load_rows(_ROOT / "withdrawals.json")


def save_withdrawals(rows: list[dict[str, Any]]) -> None:
    _save_rows(_ROOT / "withdrawals.json", rows)


def merge_withdrawals(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {(str(r["date"]), r["coin"], r["amount"]) for r in existing}
    merged = existing + [r for r in fresh if (str(r["date"]), r["coin"], r["amount"]) not in seen]
    merged.sort(key=lambda r: str(r.get("date", "")))
    return merged


# ── Reconstructed daily balances ───────────────────────────────────────────

def load_daily_balances() -> dict[date, dict[str, float]]:
    p = _ROOT / "balances.json"
    if not p.exists():
        return {}
    return {date.fromisoformat(k): v for k, v in json.loads(p.read_text()).items()}


def save_daily_balances(balances: dict[date, dict[str, float]]) -> None:
    _mkdir()
    (_ROOT / "balances.json").write_text(
        json.dumps({str(d): coins for d, coins in sorted(balances.items())}, indent=2)
    )


# ── Metadata ───────────────────────────────────────────────────────────────

def load_metadata() -> dict[str, Any]:
    p = _ROOT / "metadata.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save_metadata(data: dict[str, Any]) -> None:
    _mkdir()
    (_ROOT / "metadata.json").write_text(json.dumps(data, indent=2))
