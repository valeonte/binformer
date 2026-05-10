"""Shared fixtures for binformer tests."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


@pytest.fixture()
def inception() -> date:
    return date(2026, 4, 6)


@pytest.fixture()
def btc_prices() -> pd.Series:
    """10-day BTC price series starting at inception."""
    dates = pd.date_range("2026-04-06", periods=10, freq="D").date
    prices = [80_000.0 + i * 500 for i in range(10)]
    return pd.Series(prices, index=pd.Index(dates, name="date"), name="close")


@pytest.fixture()
def eth_prices() -> pd.Series:
    dates = pd.date_range("2026-04-06", periods=10, freq="D").date
    prices = [2_000.0 + i * 20 for i in range(10)]
    return pd.Series(prices, index=pd.Index(dates, name="date"), name="close")


@pytest.fixture()
def usdt_values() -> pd.Series:
    """Portfolio USDT value series — grows 1% per day with no cash flows."""
    dates = pd.date_range("2026-04-06", periods=10, freq="D").date
    values = [10_000.0 * (1.01**i) for i in range(10)]
    return pd.Series(values, index=pd.Index(dates, name="date"), name="usdt_value")


@pytest.fixture()
def empty_cf() -> pd.Series:
    return pd.Series(dtype=float, name="net_cf").rename_axis("date")


@pytest.fixture()
def cf_with_deposit() -> pd.Series:
    """A single $1000 deposit on day 3."""
    return pd.Series(
        [1_000.0],
        index=pd.Index([date(2026, 4, 9)], name="date"),
        name="net_cf",
    )
