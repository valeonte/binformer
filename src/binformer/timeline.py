"""Chronological account timeline: transactions + daily balance snapshots printed to stderr."""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from binformer.binance import STABLECOINS


def _price(coin: str, prices: dict[str, pd.Series], dt: Any) -> float | None:
    if coin in STABLECOINS:
        return 1.0
    series = prices.get(coin)
    if series is None or series.empty:
        return None
    candidates = series[series.index <= dt]
    return float(candidates.iloc[-1]) if not candidates.empty else None


def _total_usdt(
    balances: dict[str, float],
    dt: Any,
    prices: dict[str, pd.Series],
    overrides: dict[str, float] | None = None,
) -> float:
    total = 0.0
    for coin, amount in balances.items():
        if abs(amount) <= 1e-10:
            continue
        p = (overrides or {}).get(coin) or _price(coin, prices, dt)
        if p is not None:
            total += amount * p
    return total


def _print_snapshot(
    label: str,
    dt: Any,
    balances: dict[str, float],
    prices: dict[str, pd.Series],
    price_dt: Any = None,
) -> None:
    p_dt = price_dt if price_dt is not None else dt
    total = 0.0
    lines: list[str] = []
    for coin in sorted(balances):
        amount = balances[coin]
        if abs(amount) <= 1e-10:
            continue
        p = _price(coin, prices, p_dt)
        if p is not None:
            val = amount * p
            total += val
            lines.append(f"    {coin}: {amount:.8f} × ${p:.4f} = ${val:.4f}")
        else:
            lines.append(f"    {coin}: {amount:.8f} (price unknown)")
    print(f"  ── {label} {dt} ──", file=sys.stderr)
    for line in lines:
        print(line, file=sys.stderr)
    print(f"    TOTAL = ${total:.4f}", file=sys.stderr)


def _parse_symbol(symbol: str) -> tuple[str, str]:
    for q in ("USDT", "USDC", "BUSD", "FDUSD", "BTC", "ETH", "BNB"):
        if symbol.endswith(q) and len(symbol) > len(q):
            return symbol[: -len(q)], q
    return symbol[:-4], symbol[-4:]


def _reconcile(
    balances: dict[str, float],
    snap: dict[str, float],
    dt: date,
) -> None:
    """Overwrite balances with Binance-reported values; log any corrections."""
    diffs: list[str] = []
    all_coins = set(balances.keys()) | set(snap.keys())
    for coin in sorted(all_coins):
        had = balances.get(coin, 0.0)
        got = snap.get(coin, 0.0)
        if abs(had - got) > 1e-6:
            diffs.append(f"    {coin}: {had:.8f} → {got:.8f}")
        balances[coin] = got
    if diffs:
        print(f"  [Reconciled with Binance snapshot {dt}]", file=sys.stderr)
        for line in diffs:
            print(line, file=sys.stderr)


def print_account_timeline(
    deposits_df: pd.DataFrame,
    trades: list[dict[str, Any]],
    prices: dict[str, pd.Series],
    snapshot_balances: dict[date, dict[str, float]] | None = None,
    starting_usdt: float = 0.0,
    binance_snapshots: dict[date, dict[str, float]] | None = None,
) -> dict[date, dict[str, float]]:
    """Print a chronological account timeline to stderr and return reconstructed daily balances."""

    events: list[dict[str, Any]] = []

    for _, row in deposits_df.iterrows():
        events.append({
            "kind": "deposit",
            "source": row.get("source", "onchain"),
            "time_ms": int(row["time_ms"]) if "time_ms" in row.index else 0,
            "date": row["date"],
            "coin": row["coin"],
            "amount": float(row["amount"]),
        })

    for t in trades:
        dt = datetime.fromtimestamp(int(t["time"]) / 1000, tz=UTC).date()
        base, quote = _parse_symbol(t["symbol"])
        events.append({
            "kind": "trade",
            "time_ms": int(t["time"]),
            "date": dt,
            "base": base,
            "quote": quote,
            "is_buyer": bool(t["isBuyer"]),
            "qty": float(t["qty"]),
            "quote_qty": float(t["quoteQty"]),
            "commission": float(t["commission"]),
            "commission_asset": t["commissionAsset"],
            "price": float(t["price"]),
        })

    events.sort(key=lambda e: (e["date"], e["time_ms"]))

    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        by_day[e["date"]].append(e)

    balances: dict[str, float] = defaultdict(float)
    daily_result: dict[date, dict[str, float]] = {}

    first_event_day = min(by_day) if by_day else date.today()
    today = date.today()
    current_day = first_event_day

    if starting_usdt > 0:
        balances["USDT"] = starting_usdt
        print(f"  [Starting balance: USDT {starting_usdt:.4f}]", file=sys.stderr)
    elif snapshot_balances:
        prior = {d: b for d, b in snapshot_balances.items() if d < first_event_day}
        if prior:
            init_date = max(prior)
            for coin, amount in prior[init_date].items():
                if abs(amount) > 1e-10:
                    balances[coin] = amount
            print(f"  [Initial balance from snapshot {init_date}]", file=sys.stderr)
        else:
            earliest = min(snapshot_balances)
            if earliest > first_event_day:
                print(
                    f"  [No snapshot before {first_event_day}; "
                    f"starting from earliest snapshot {earliest}]",
                    file=sys.stderr,
                )
                for coin, amount in snapshot_balances[earliest].items():
                    if abs(amount) > 1e-10:
                        balances[coin] = amount
                current_day = earliest

    # Record the state one day before the first tracked event so that
    # usdt_values.iloc[0] reflects true initial capital, not post-deposit value.
    daily_result[current_day - timedelta(days=1)] = {
        c: a for c, a in balances.items() if abs(a) > 1e-10
    }

    while current_day <= today:
        prev_day = current_day - timedelta(days=1)
        if current_day in by_day:
            _print_snapshot("Start of", current_day, balances, prices, price_dt=prev_day)

            for e in by_day[current_day]:
                if e["kind"] == "deposit":
                    coin, amount = e["coin"], e["amount"]
                    balances[coin] += amount
                    total = _total_usdt(balances, current_day, prices)
                    label = "[buy crypto]" if e["source"] == "fiat" else "[deposit]"
                    print(f"  {label} +{amount:.4f} {coin} => total ${total:.4f}", file=sys.stderr)

                elif e["kind"] == "trade":
                    base, quote = e["base"], e["quote"]
                    is_buyer = e["is_buyer"]
                    trade_price = e["price"]

                    overrides: dict[str, float] = {}
                    if quote in STABLECOINS:
                        overrides[base] = trade_price
                    elif base in STABLECOINS:
                        overrides[quote] = 1.0 / trade_price if trade_price > 0 else 0.0

                    total_before = _total_usdt(balances, current_day, prices, overrides)

                    if is_buyer:
                        balances[base] += e["qty"]
                        balances[quote] -= e["quote_qty"]
                    else:
                        balances[base] -= e["qty"]
                        balances[quote] += e["quote_qty"]
                    balances[e["commission_asset"]] -= e["commission"]

                    total_after = _total_usdt(balances, current_day, prices, overrides)
                    delta = total_after - total_before
                    sign = "+" if delta >= 0 else ""
                    action = f"buy {base} using {quote}" if is_buyer else f"sell {base} for {quote}"
                    print(
                        f"  [{action}] {sign}{delta:.4f} => total ${total_after:.4f}",
                        file=sys.stderr,
                    )

            if binance_snapshots and current_day in binance_snapshots:
                _reconcile(balances, binance_snapshots[current_day], current_day)

            _print_snapshot("End of", current_day, balances, prices)
            print(file=sys.stderr)
        else:
            if binance_snapshots and current_day in binance_snapshots:
                _reconcile(balances, binance_snapshots[current_day], current_day)
            total = _total_usdt(balances, current_day, prices)
            print(f"  {current_day}: ${total:.4f}", file=sys.stderr)

        daily_result[current_day] = {c: a for c, a in balances.items() if abs(a) > 1e-10}
        current_day += timedelta(days=1)

    return daily_result
