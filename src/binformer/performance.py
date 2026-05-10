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

    rows.append(_row("Since Inception", inception))
    rows.append(_row("YTD", date(today.year, 1, 1)))
    rows.append(_row("MTD", date(today.year, today.month, 1)))
    rows.append(_row("Last 7 days", today - timedelta(days=7)))
    rows.append(_row("Last 30 days", today - timedelta(days=30)))

    for months, label in [(1, "Last 1M"), (3, "Last 3M"), (6, "Last 6M"), (12, "Last 1Y")]:
        candidate = today - relativedelta(months=months)
        if candidate < inception:
            rows.append(PeriodResult(label, None, None, None))
        else:
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
