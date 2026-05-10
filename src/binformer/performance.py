"""Performance calculation: TWR, period returns, money metrics, cumulative returns."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from dateutil.relativedelta import relativedelta

from binformer.binance import STABLECOINS

INCEPTION_DATE = date(2026, 4, 6)


@dataclass
class PeriodResult:
    label: str
    strategy: float | None
    btc: float | None
    eth: float | None


@dataclass
class HoldingRow:
    coin: str
    amount: float
    price: float | None
    usdt_value: float
    change_usdt: float | None
    change_pct: float | None


@dataclass
class MoneyMetrics:
    inception_date: date
    report_date: date
    days_live: int
    start_value_usdt: float
    total_deposits_usdt: float
    total_withdrawals_usdt: float
    net_deposits_usdt: float
    current_value_usdt: float
    gross_pnl_usdt: float
    twr_pct: float


def cash_flows_to_usdt(
    deposits: pd.DataFrame,
    withdrawals: pd.DataFrame,
    btc_prices: pd.Series,
    eth_prices: pd.Series,
) -> pd.Series:
    """Convert deposit/withdrawal DataFrames to a daily net cash-flow Series in USDT.

    Positive = net inflow, negative = net outflow.
    """
    result: dict[date, float] = {}

    def _convert(row: pd.Series, sign: float) -> None:  # type: ignore[type-arg]
        coin: str = row["coin"]
        amount: float = float(row["amount"])
        dt: date = row["date"]

        if coin in STABLECOINS:
            usdt = amount
        elif coin == "BTC":
            price = _price_on(btc_prices, dt)
            if price is None:
                print(f"Warning: no BTC price for {dt}, skipping", file=sys.stderr)
                return
            usdt = amount * price
        elif coin == "ETH":
            price = _price_on(eth_prices, dt)
            if price is None:
                print(f"Warning: no ETH price for {dt}, skipping", file=sys.stderr)
                return
            usdt = amount * price
        else:
            print(f"Warning: unsupported coin {coin} on {dt}, skipping", file=sys.stderr)
            return

        result[dt] = result.get(dt, 0.0) + sign * usdt

    if not deposits.empty:
        deposits.apply(_convert, axis=1, sign=1.0)  # type: ignore[call-arg]
    if not withdrawals.empty:
        withdrawals.apply(_convert, axis=1, sign=-1.0)  # type: ignore[call-arg]

    if not result:
        return pd.Series(dtype=float, name="net_cf").rename_axis("date")
    return pd.Series(result, name="net_cf").rename_axis("date").sort_index()


def snapshots_to_usdt(
    snapshots: pd.DataFrame, btc_prices: pd.Series, eth_prices: pd.Series
) -> pd.Series:
    """Convert snapshots to USDT, pricing BTC/ETH/stablecoins directly to avoid double-conversion.

    totalAssetOfBtc is computed by Binance at snapshot time using the BTC price then; multiplying
    it by a different close price introduces error. Instead we price known assets directly and
    use totalAssetOfBtc only for residual coins we don't track individually.
    """
    btc = btc_prices.reindex(snapshots.index, method="ffill")
    eth = eth_prices.reindex(snapshots.index, method="ffill")
    known_usdt = snapshots["usdt_free"] + snapshots["btc_free"] * btc + snapshots["eth_free"] * eth
    # Residual: assets beyond BTC/ETH/stablecoins, approximated via totalAssetOfBtc.
    residual_btc = (
        snapshots["total_btc"]
        - snapshots["btc_free"]
        - snapshots["usdt_free"] / btc
        - snapshots["eth_free"] * eth / btc
    ).clip(lower=0)
    return (known_usdt + residual_btc * btc).rename("usdt_value").dropna()


def reconstructed_usdt_values(
    daily_balances: dict[date, dict[str, float]],
    prices: dict[str, pd.Series],
) -> pd.Series:
    """Convert reconstructed daily coin balances to a USDT value series."""
    result: dict[date, float] = {}
    for d, coins in sorted(daily_balances.items()):
        total = 0.0
        for coin, amount in coins.items():
            if abs(amount) <= 1e-10:
                continue
            if coin in STABLECOINS:
                total += amount
                continue
            series = prices.get(coin)
            if series is None or series.empty:
                continue
            candidates = series[series.index <= d]
            if not candidates.empty:
                total += amount * float(candidates.iloc[-1])
        result[d] = total
    if not result:
        return pd.Series(dtype=float, name="usdt_value").rename_axis("date")
    return pd.Series(result, name="usdt_value").rename_axis("date")


def hypothetical_coin_values(
    usdt_values: pd.Series,
    net_cf: pd.Series,
    coin_prices: pd.Series,
) -> pd.Series:
    """USDT value of an all-in position in a single coin.

    Starts with the same capital as the portfolio, and converts every cash flow
    (deposit/withdrawal) into the coin at that day's price.
    """
    if usdt_values.empty:
        return pd.Series(dtype=float, name="usdt_value").rename_axis("date")

    aligned = coin_prices.reindex(usdt_values.index, method="ffill")
    p_start = float(aligned.iloc[0]) if not pd.isna(aligned.iloc[0]) else None
    if not p_start or p_start <= 0:
        return pd.Series(dtype=float, name="usdt_value").rename_axis("date")

    holdings = float(usdt_values.iloc[0]) / p_start
    result: dict[date, float] = {}

    for i, d in enumerate(usdt_values.index):
        p_raw = aligned.iloc[i]
        if pd.isna(p_raw) or float(p_raw) <= 0:
            continue
        p = float(p_raw)
        if i > 0:
            cf = float(net_cf.get(d, 0.0)) if d in net_cf.index else 0.0
            if cf != 0:
                holdings += cf / p
        result[d] = holdings * p

    return pd.Series(result, name="usdt_value").rename_axis("date")


def pnl_series(
    value_series: pd.Series,
    net_cf: pd.Series,
) -> pd.Series:
    """Trading PnL over time, stripping out invested capital.

    pnl(t) = value(t) - starting_value - cumulative_net_flows(t)

    Starts at 0 on the first date. The final value matches gross_pnl in MoneyMetrics
    when net_cf is the post-start cash flow series (net_cf_after).
    """
    if value_series.empty:
        return pd.Series(dtype=float, name="pnl").rename_axis("date")
    start = float(value_series.iloc[0])
    cum_cf = net_cf.reindex(value_series.index, fill_value=0.0).cumsum()
    return (value_series - start - cum_cf).rename("pnl")


def _price_on(prices: pd.Series, d: date) -> float | None:
    candidates = prices[prices.index <= d]
    return float(candidates.iloc[-1]) if not candidates.empty else None


def _twr(usdt_values: pd.Series, net_cf: pd.Series) -> float:
    """Time-weighted return over the full supplied series."""
    if len(usdt_values) < 2:
        return 0.0
    factor = 1.0
    for i in range(1, len(usdt_values)):
        dt = usdt_values.index[i]
        v_prev = float(usdt_values.iloc[i - 1])
        v_curr = float(usdt_values.iloc[i])
        cf = float(net_cf.get(dt, 0.0)) if dt in net_cf.index else 0.0
        denom = v_prev + cf
        if denom > 0:
            factor *= v_curr / denom
    return factor - 1.0


def period_return(
    usdt_values: pd.Series,
    net_cf: pd.Series,
    start: date,
    end: date,
) -> float | None:
    """TWR for usdt_values between start and end (inclusive). None if < 2 data points."""
    mask = (usdt_values.index >= start) & (usdt_values.index <= end)
    seg = usdt_values[mask]
    if len(seg) < 2:
        return None
    seg_cf = net_cf.reindex(seg.index).fillna(0.0)
    return _twr(seg, seg_cf)


def benchmark_return(prices: pd.Series, start: date, end: date) -> float | None:
    """Simple price return for a benchmark between start and end."""
    p_start_s = prices[prices.index >= start]
    p_end_s = prices[prices.index <= end]
    if p_start_s.empty or p_end_s.empty:
        return None
    p_start = float(p_start_s.iloc[0])
    p_end = float(p_end_s.iloc[-1])
    return p_end / p_start - 1 if p_start > 0 else None


def build_performance_table(
    usdt_values: pd.Series,
    net_cf: pd.Series,
    btc_prices: pd.Series,
    eth_prices: pd.Series,
    inception: date = INCEPTION_DATE,
) -> list[PeriodResult]:
    today = usdt_values.index[-1] if not usdt_values.empty else date.today()

    def _row(label: str, start: date) -> PeriodResult:
        if start < inception:
            start = inception
        strat = period_return(usdt_values, net_cf, start, today)
        btc = benchmark_return(btc_prices, start, today)
        eth = benchmark_return(eth_prices, start, today)
        return PeriodResult(label, strat, btc, eth)

    rows: list[PeriodResult] = []

    year_start = date(today.year, 1, 1)
    rows.append(_row("Since Inception", inception))
    if inception < year_start:
        rows.append(_row("YTD", year_start))

    rows.append(_row("MTD", date(today.year, today.month, 1)))
    rows.append(_row("Last day", today - timedelta(days=1)))
    rows.append(_row("Last 7 days", today - timedelta(days=7)))
    rows.append(_row("Last 14 days", today - timedelta(days=14)))

    for months, label in [(1, "Last 1M"), (3, "Last 3M"), (6, "Last 6M"), (12, "Last 1Y")]:
        candidate = today - relativedelta(months=months)
        if candidate > inception:
            rows.append(_row(label, candidate))

    return rows


def cumulative_returns(
    usdt_values: pd.Series,
    net_cf: pd.Series,
    btc_prices: pd.Series,
    eth_prices: pd.Series,
) -> pd.DataFrame:
    """DataFrame(portfolio, btc, eth) of cumulative % returns from inception, indexed by date."""
    if usdt_values.empty:
        return pd.DataFrame(columns=["portfolio", "btc", "eth"])

    daily_r: list[float] = []
    dates: list[date] = []
    for i in range(1, len(usdt_values)):
        dt = usdt_values.index[i]
        v_prev = float(usdt_values.iloc[i - 1])
        v_curr = float(usdt_values.iloc[i])
        cf = float(net_cf.get(dt, 0.0)) if dt in net_cf.index else 0.0
        denom = v_prev + cf
        daily_r.append(v_curr / denom - 1 if denom > 0 else 0.0)
        dates.append(dt)

    inception = usdt_values.index[0]
    cum_portfolio = pd.concat(
        [
            pd.Series([0.0], index=[inception]),
            (1 + pd.Series(daily_r, index=dates)).cumprod() - 1,
        ]
    )

    btc_aligned = btc_prices.reindex(cum_portfolio.index, method="ffill")
    eth_aligned = eth_prices.reindex(cum_portfolio.index, method="ffill")
    btc_0, eth_0 = float(btc_aligned.iloc[0]), float(eth_aligned.iloc[0])

    return pd.DataFrame(
        {
            "portfolio": cum_portfolio,
            "btc": btc_aligned / btc_0 - 1,
            "eth": eth_aligned / eth_0 - 1,
        }
    )


def build_holdings(
    daily_balances: dict[date, dict[str, float]],
    prices: dict[str, pd.Series],
) -> list[HoldingRow]:
    """Current holdings with day-over-day USDT value change."""
    if not daily_balances:
        return []

    sorted_dates = sorted(daily_balances.keys())
    last_date = sorted_dates[-1]
    prev_date = sorted_dates[-2] if len(sorted_dates) >= 2 else None

    current = daily_balances[last_date]
    prev = daily_balances[prev_date] if prev_date else {}

    def _get_price(coin: str, d: date) -> float | None:
        if coin in STABLECOINS:
            return 1.0
        series = prices.get(coin)
        if series is None or series.empty:
            return None
        candidates = series[series.index <= d]
        return float(candidates.iloc[-1]) if not candidates.empty else None

    rows: list[HoldingRow] = []
    for coin, amount in current.items():
        if abs(amount) <= 1e-6:
            continue
        price = _get_price(coin, last_date)
        usdt_value = amount * price if price is not None else 0.0

        prev_amount = prev.get(coin, 0.0)
        if prev_date is not None:
            prev_price = _get_price(coin, prev_date)
            prev_usdt: float | None = (prev_amount * prev_price) if prev_price is not None else None
        else:
            prev_usdt = None

        if prev_usdt is not None:
            change_usdt: float | None = usdt_value - prev_usdt
            change_pct: float | None = (
                change_usdt / prev_usdt * 100 if abs(prev_usdt) > 1e-10 else None
            )
        else:
            change_usdt = None
            change_pct = None

        rows.append(HoldingRow(
            coin=coin,
            amount=amount,
            price=price,
            usdt_value=usdt_value,
            change_usdt=change_usdt,
            change_pct=change_pct,
        ))

    rows.sort(key=lambda r: r.usdt_value, reverse=True)
    return rows


def compute_money_metrics(
    usdt_values: pd.Series,
    net_cf: pd.Series,
    deposits_usdt: float,
    withdrawals_usdt: float,
    inception: date = INCEPTION_DATE,
) -> MoneyMetrics:
    today = usdt_values.index[-1] if not usdt_values.empty else date.today()
    start_value = float(usdt_values.iloc[0]) if not usdt_values.empty else 0.0
    current_value = float(usdt_values.iloc[-1]) if not usdt_values.empty else 0.0
    net_dep = deposits_usdt - withdrawals_usdt
    gross_pnl = current_value - start_value - net_dep
    twr = _twr(usdt_values, net_cf)

    return MoneyMetrics(
        inception_date=inception,
        report_date=today,
        days_live=(today - inception).days,
        start_value_usdt=start_value,
        total_deposits_usdt=deposits_usdt,
        total_withdrawals_usdt=withdrawals_usdt,
        net_deposits_usdt=net_dep,
        current_value_usdt=current_value,
        gross_pnl_usdt=gross_pnl,
        twr_pct=twr * 100,
    )
