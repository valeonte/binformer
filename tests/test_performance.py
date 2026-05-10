"""Tests for performance calculation logic."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from binformer.performance import (
    benchmark_return,
    build_performance_table,
    cash_flows_to_usdt,
    compute_money_metrics,
    cumulative_returns,
    period_return,
    snapshots_to_usdt,
)


class TestPeriodReturn:
    def test_no_cashflows_matches_simple_return(
        self, usdt_values: pd.Series, empty_cf: pd.Series
    ) -> None:
        start = usdt_values.index[0]
        end = usdt_values.index[-1]
        result = period_return(usdt_values, empty_cf, start, end)
        assert result is not None
        # 1.01^9 - 1
        expected = 1.01**9 - 1
        assert abs(result - expected) < 1e-6

    def test_single_day_returns_none(self, usdt_values: pd.Series, empty_cf: pd.Series) -> None:
        start = end = usdt_values.index[0]
        assert period_return(usdt_values, empty_cf, start, end) is None

    def test_period_before_data_returns_none(
        self, usdt_values: pd.Series, empty_cf: pd.Series
    ) -> None:
        result = period_return(usdt_values, empty_cf, date(2020, 1, 1), date(2020, 12, 31))
        assert result is None

    def test_deposit_reduces_measured_return(
        self, usdt_values: pd.Series, cf_with_deposit: pd.Series
    ) -> None:
        start = usdt_values.index[0]
        end = usdt_values.index[-1]
        r_no_cf = period_return(usdt_values, pd.Series(dtype=float).rename_axis("date"), start, end)
        r_with_cf = period_return(usdt_values, cf_with_deposit, start, end)
        assert r_no_cf is not None and r_with_cf is not None
        # A deposit inflates the denominator on that day, lowering the measured return
        assert r_with_cf < r_no_cf


class TestBenchmarkReturn:
    def test_correct_simple_return(self, btc_prices: pd.Series) -> None:
        start = btc_prices.index[0]
        end = btc_prices.index[-1]
        result = benchmark_return(btc_prices, start, end)
        expected = btc_prices.iloc[-1] / btc_prices.iloc[0] - 1
        assert result is not None
        assert abs(result - expected) < 1e-9

    def test_returns_none_when_no_data(self, btc_prices: pd.Series) -> None:
        assert benchmark_return(btc_prices, date(2020, 1, 1), date(2020, 12, 31)) is None

    def test_zero_return_flat_prices(self) -> None:
        dates = pd.date_range("2026-04-06", periods=5, freq="D").date
        prices = pd.Series([100.0] * 5, index=pd.Index(dates, name="date"))
        assert benchmark_return(prices, dates[0], dates[-1]) == pytest.approx(0.0)


class TestSnapshotsToUsdt:
    def test_conversion(self, btc_prices: pd.Series) -> None:
        dates = btc_prices.index.tolist()[:3]
        snaps = pd.DataFrame(
            {"total_btc": [1.0, 1.0, 1.0]},
            index=pd.Index(dates, name="date"),
        )
        result = snapshots_to_usdt(snaps, btc_prices)
        for d in dates:
            assert result[d] == pytest.approx(btc_prices[d])


class TestCashFlowsToUsdt:
    def test_usdt_deposit_passthrough(self, btc_prices: pd.Series, eth_prices: pd.Series) -> None:
        dep = pd.DataFrame([{"date": date(2026, 4, 8), "coin": "USDT", "amount": 500.0}])
        wd = pd.DataFrame(columns=["date", "coin", "amount"])
        result = cash_flows_to_usdt(dep, wd, btc_prices, eth_prices)
        assert result[date(2026, 4, 8)] == pytest.approx(500.0)

    def test_btc_deposit_converted(self, btc_prices: pd.Series, eth_prices: pd.Series) -> None:
        dep = pd.DataFrame([{"date": date(2026, 4, 6), "coin": "BTC", "amount": 0.1}])
        wd = pd.DataFrame(columns=["date", "coin", "amount"])
        result = cash_flows_to_usdt(dep, wd, btc_prices, eth_prices)
        expected = 0.1 * 80_000.0
        assert result[date(2026, 4, 6)] == pytest.approx(expected)

    def test_withdrawal_is_negative(self, btc_prices: pd.Series, eth_prices: pd.Series) -> None:
        dep = pd.DataFrame(columns=["date", "coin", "amount"])
        wd = pd.DataFrame([{"date": date(2026, 4, 6), "coin": "USDT", "amount": 200.0}])
        result = cash_flows_to_usdt(dep, wd, btc_prices, eth_prices)
        assert result[date(2026, 4, 6)] == pytest.approx(-200.0)

    def test_empty_returns_empty_series(self, btc_prices: pd.Series, eth_prices: pd.Series) -> None:
        dep = pd.DataFrame(columns=["date", "coin", "amount"])
        wd = pd.DataFrame(columns=["date", "coin", "amount"])
        result = cash_flows_to_usdt(dep, wd, btc_prices, eth_prices)
        assert result.empty


class TestCumulativeReturns:
    def test_starts_at_zero(
        self,
        usdt_values: pd.Series,
        empty_cf: pd.Series,
        btc_prices: pd.Series,
        eth_prices: pd.Series,
    ) -> None:
        result = cumulative_returns(usdt_values, empty_cf, btc_prices, eth_prices)
        assert result["portfolio"].iloc[0] == pytest.approx(0.0)
        assert result["btc"].iloc[0] == pytest.approx(0.0)
        assert result["eth"].iloc[0] == pytest.approx(0.0)

    def test_empty_usdt_returns_empty(
        self, empty_cf: pd.Series, btc_prices: pd.Series, eth_prices: pd.Series
    ) -> None:
        empty = pd.Series(dtype=float, name="usdt_value")
        result = cumulative_returns(empty, empty_cf, btc_prices, eth_prices)
        assert result.empty


class TestBuildPerformanceTable:
    def test_returns_correct_number_of_rows(
        self,
        usdt_values: pd.Series,
        empty_cf: pd.Series,
        btc_prices: pd.Series,
        eth_prices: pd.Series,
        inception: date,
    ) -> None:
        rows = build_performance_table(usdt_values, empty_cf, btc_prices, eth_prices, inception)
        assert len(rows) == 9

    def test_insufficient_data_rows_are_none(
        self,
        usdt_values: pd.Series,
        empty_cf: pd.Series,
        btc_prices: pd.Series,
        eth_prices: pd.Series,
        inception: date,
    ) -> None:
        rows = build_performance_table(usdt_values, empty_cf, btc_prices, eth_prices, inception)
        long_period = next(r for r in rows if r.label == "Last 3M")
        assert long_period.strategy is None

    def test_since_inception_matches_full_twr(
        self,
        usdt_values: pd.Series,
        empty_cf: pd.Series,
        btc_prices: pd.Series,
        eth_prices: pd.Series,
        inception: date,
    ) -> None:
        rows = build_performance_table(usdt_values, empty_cf, btc_prices, eth_prices, inception)
        row = next(r for r in rows if r.label == "Since Inception")
        expected = 1.01**9 - 1
        assert row.strategy is not None
        assert abs(row.strategy - expected) < 1e-6


class TestMoneyMetrics:
    def test_gross_pnl_no_cashflows(
        self, usdt_values: pd.Series, empty_cf: pd.Series, inception: date
    ) -> None:
        metrics = compute_money_metrics(usdt_values, empty_cf, 0.0, 0.0, inception)
        expected_pnl = usdt_values.iloc[-1] - usdt_values.iloc[0]
        assert abs(metrics.gross_pnl_usdt - expected_pnl) < 1e-6

    def test_gross_pnl_with_deposit(
        self, usdt_values: pd.Series, cf_with_deposit: pd.Series, inception: date
    ) -> None:
        metrics = compute_money_metrics(usdt_values, cf_with_deposit, 1_000.0, 0.0, inception)
        expected_pnl = usdt_values.iloc[-1] - usdt_values.iloc[0] - 1_000.0
        assert abs(metrics.gross_pnl_usdt - expected_pnl) < 1e-6

    def test_days_live(self, usdt_values: pd.Series, empty_cf: pd.Series, inception: date) -> None:
        metrics = compute_money_metrics(usdt_values, empty_cf, 0.0, 0.0, inception)
        last_date = usdt_values.index[-1]
        assert metrics.days_live == (last_date - inception).days
