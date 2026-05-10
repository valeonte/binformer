"""Binance REST API client — account snapshots, deposits, withdrawals, klines."""

from __future__ import annotations

import hashlib
import hmac
import sys
import time
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

BINANCE_BASE = "https://api.binance.com"
STABLECOINS = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USDP"}
INCEPTION_DATE = date(2026, 4, 1)


def _to_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)


def _ms_to_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).date()


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self._secret = api_secret
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": api_key})
        self.snapshot_coin_balances: dict[date, dict[str, float]] = {}

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

        rows = []
        for s in all_snaps:
            d = s["data"]
            bal_map = {b["asset"]: float(b["free"]) + float(b["locked"]) for b in d.get("balances", [])}
            snap_date = _ms_to_date(s["updateTime"])
            self.snapshot_coin_balances[snap_date] = {
                asset: amount for asset, amount in bal_map.items() if amount > 1e-10
            }
            rows.append({
                "date": _ms_to_date(s["updateTime"]),
                "total_btc": float(d["totalAssetOfBtc"]),
                "btc_free": bal_map.get("BTC", 0.0),
                "eth_free": bal_map.get("ETH", 0.0),
                "usdt_free": sum(bal_map.get(sc, 0.0) for sc in STABLECOINS),
            })
        if not rows:
            return pd.DataFrame(columns=["total_btc", "btc_free", "eth_free", "usdt_free"]).rename_axis("date")
        return pd.DataFrame(rows).drop_duplicates("date").set_index("date").sort_index()

    def get_deposits(self, start_date: date) -> pd.DataFrame:
        """Successful deposits since start_date. Returns DataFrame(date, coin, amount).

        Covers both on-chain crypto deposits and fiat 'Buy Crypto' purchases.
        """
        rows: list[dict[str, Any]] = []

        # On-chain crypto deposits
        offset = 0
        while True:
            batch: list[dict[str, Any]] = self._get(
                "/sapi/v1/capital/deposit/hisrec",
                {"startTime": _to_ms(start_date), "status": 1, "limit": 1000, "offset": offset},
                signed=True,
            )
            for dep in batch:
                time_ms = int(dep["insertTime"])
                dt = _ms_to_date(time_ms)
                coin = dep["coin"]
                amount = float(dep["amount"])
                print(f"[deposit]     {dt}  {amount:>12.6f} {coin}", file=sys.stderr)
                rows.append({"date": dt, "time_ms": time_ms, "coin": coin, "amount": amount, "source": "onchain"})
            if len(batch) < 1000:
                break
            offset += 1000

        # Fiat "Buy Crypto" purchases (show as "Buy Crypto Successful" in the app)
        page = 1
        while True:
            data: dict[str, Any] = self._get(
                "/sapi/v1/fiat/payments",
                {"transactionType": 0, "beginTime": _to_ms(start_date), "page": page, "rows": 500},
                signed=True,
            )
            batch_fiat: list[dict[str, Any]] = data.get("data", [])
            for item in batch_fiat:
                if item.get("status") != "Completed":
                    continue
                time_ms = int(item["createTime"])
                dt = _ms_to_date(time_ms)
                coin = item["cryptoCurrency"]
                amount = float(item["obtainAmount"])
                fiat_amt = item.get("sourceAmount", "?")
                fiat_cur = item.get("fiatCurrency", "")
                print(
                    f"[buy crypto]  {dt}  {amount:>12.6f} {coin:<6} (paid {fiat_amt} {fiat_cur})",
                    file=sys.stderr,
                )
                rows.append({"date": dt, "time_ms": time_ms, "coin": coin, "amount": amount, "source": "fiat"})
            if len(batch_fiat) < 500:
                break
            page += 1

        cols = ["date", "time_ms", "coin", "amount", "source"]
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)

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

    def get_current_coins(self) -> set[str]:
        """Non-stablecoin assets with any non-zero spot balance."""
        data: dict[str, Any] = self._get("/api/v3/account", {}, signed=True)
        return {
            b["asset"]
            for b in data["balances"]
            if float(b["free"]) + float(b["locked"]) > 1e-8 and b["asset"] not in STABLECOINS
        }

    def get_trade_symbols(self, deposit_coins: set[str]) -> list[str]:
        """XUSDT symbols: current holdings + deposit coins + snapshot coins + BTC/ETH."""
        current = self.get_current_coins()
        snapshot_coins = {coin for snap in self.snapshot_coin_balances.values() for coin in snap}
        all_coins = (current | deposit_coins | snapshot_coins) - STABLECOINS
        return sorted({f"{c}USDT" for c in all_coins} | {"BTCUSDT", "ETHUSDT"})

    def get_trades(self, symbols: list[str], start_date: date) -> list[dict[str, Any]]:
        """All executed trades for the given symbols since start_date, sorted by time."""
        all_trades: list[dict[str, Any]] = []
        start_ms = _to_ms(start_date)
        for symbol in symbols:
            try:
                batch: list[dict[str, Any]] = self._get(
                    "/api/v3/myTrades",
                    {"symbol": symbol, "startTime": start_ms, "limit": 1000},
                    signed=True,
                )
                while batch:
                    all_trades.extend(batch)
                    if len(batch) < 1000:
                        break
                    from_id = int(batch[-1]["id"]) + 1
                    batch = self._get(
                        "/api/v3/myTrades",
                        {"symbol": symbol, "fromId": from_id, "limit": 1000},
                        signed=True,
                    )
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 400:
                    pass  # invalid symbol — skip silently
                else:
                    raise
        all_trades.sort(key=lambda t: int(t["time"]))
        return all_trades

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
