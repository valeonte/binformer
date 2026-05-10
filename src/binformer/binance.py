"""Binance REST API client — account snapshots, deposits, withdrawals, klines."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

BINANCE_BASE = "https://api.binance.com"
STABLECOINS = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USDP"}
INCEPTION_DATE = date(2026, 4, 6)


def _to_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)


def _ms_to_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).date()


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self._secret = api_secret
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": api_key})

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params["timestamp"] = int(time.time() * 1000)
        qs = urlencode(params)
        sig = hmac.new(self._secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        return params

    def _get(self, path: str, params: dict[str, Any], signed: bool = False) -> Any:
        if signed:
            params = self._sign(dict(params))
        resp = self._session.get(f"{BINANCE_BASE}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_account_snapshots(self, start_date: date) -> pd.DataFrame:
        """Daily spot account snapshots. Returns DataFrame(total_btc) indexed by date."""
        all_snaps: list[dict[str, Any]] = []
        start_ms = _to_ms(start_date)
        end_ms = int(time.time() * 1000)

        while True:
            data = self._get(
                "/sapi/v1/accountSnapshot",
                {"type": "SPOT", "startTime": start_ms, "endTime": end_ms, "limit": 30},
                signed=True,
            )
            batch: list[dict[str, Any]] = data.get("snapshotVos", [])
            all_snaps.extend(batch)
            if len(batch) < 30:
                break
            start_ms = batch[-1]["updateTime"] + 86_400_000
            if start_ms >= end_ms:
                break

        rows = [
            {"date": _ms_to_date(s["updateTime"]), "total_btc": float(s["data"]["totalAssetOfBtc"])}
            for s in all_snaps
        ]
        if not rows:
            return pd.DataFrame(columns=["total_btc"]).rename_axis("date")
        return pd.DataFrame(rows).drop_duplicates("date").set_index("date").sort_index()

    def get_deposits(self, start_date: date) -> pd.DataFrame:
        """Successful deposits since start_date. Returns DataFrame(date, coin, amount)."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch: list[dict[str, Any]] = self._get(
                "/sapi/v1/capital/deposit/hisrec",
                {"startTime": _to_ms(start_date), "status": 1, "limit": 1000, "offset": offset},
                signed=True,
            )
            for dep in batch:
                rows.append(
                    {
                        "date": _ms_to_date(int(dep["insertTime"])),
                        "coin": dep["coin"],
                        "amount": float(dep["amount"]),
                    }
                )
            if len(batch) < 1000:
                break
            offset += 1000

        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "coin", "amount"])

    def get_withdrawals(self, start_date: date) -> pd.DataFrame:
        """Completed withdrawals since start_date. Returns DataFrame(date, coin, amount)."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch: list[dict[str, Any]] = self._get(
                "/sapi/v1/capital/withdraw/history",
                {"startTime": _to_ms(start_date), "status": 6, "limit": 1000, "offset": offset},
                signed=True,
            )
            for wd in batch:
                apply_time = wd["applyTime"]
                if isinstance(apply_time, str):
                    dt = datetime.strptime(apply_time, "%Y-%m-%d %H:%M:%S").date()
                else:
                    dt = _ms_to_date(int(apply_time))
                rows.append({"date": dt, "coin": wd["coin"], "amount": float(wd["amount"])})
            if len(batch) < 1000:
                break
            offset += 1000

        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "coin", "amount"])

    def get_klines(self, symbol: str, start_date: date) -> pd.Series:
        """Daily close prices for symbol since start_date. Returns Series indexed by date."""
        all_klines: list[Any] = []
        start_ms = _to_ms(start_date)

        while True:
            batch: list[Any] = self._get(
                "/api/v3/klines",
                {"symbol": symbol, "interval": "1d", "startTime": start_ms, "limit": 1000},
            )
            all_klines.extend(batch)
            if len(batch) < 1000:
                break
            start_ms = batch[-1][0] + 86_400_000

        if not all_klines:
            return pd.Series(dtype=float, name="close")
        dates = [_ms_to_date(k[0]) for k in all_klines]
        closes = [float(k[4]) for k in all_klines]
        return pd.Series(closes, index=pd.Index(dates, name="date"), name="close")
