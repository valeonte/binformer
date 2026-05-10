"""Generate a base64-encoded normalised-return chart (portfolio vs BTC vs ETH)."""

from __future__ import annotations

import base64
import io

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

_COLORS = {
    "portfolio": "#3b82f6",
    "btc": "#f59e0b",
    "eth": "#8b5cf6",
}
_LABELS = {
    "portfolio": "Strategy",
    "btc": "BTC",
    "eth": "ETH",
}


def build_absolute_chart(
    strategy_pnl: pd.Series,
    btc_pnl: pd.Series,
    eth_pnl: pd.Series,
    width: int = 700,
    height: int = 350,
) -> str:
    """Return a base64-encoded PNG of trading PnL (starting capital + deposits stripped out).

    All three series start at 0. Final values in legend show net gain/loss in USDT.
    """
    dpi = 96
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    series_cfg = [
        (strategy_pnl, "#3b82f6", "Strategy", 2.0, 3),
        (btc_pnl, "#f59e0b", "BTC-only", 1.4, 2),
        (eth_pnl, "#8b5cf6", "ETH-only", 1.4, 2),
    ]
    for series, color, label, lw, z in series_cfg:
        if series.empty:
            continue
        final = float(series.iloc[-1])
        sign = "+" if final >= 0 else ""
        full_label = f"{label}  {sign}${final:,.0f}"
        ax.plot(
            pd.to_datetime(series.index),
            series,
            label=full_label,
            color=color,
            linewidth=lw,
            zorder=z,
        )

    ax.axhline(0, color="#94a3b8", linewidth=0.8, linestyle="--", zorder=1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:+,.0f}" if v != 0 else "$0"))
    ax.tick_params(axis="y", labelsize=8)
    ax.set_ylabel("PnL (USDT)", fontsize=9)
    ax.legend(fontsize=9, framealpha=0.9)
    ax.grid(axis="y", color="#e2e8f0", linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout(pad=1.2)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def build_chart(cum_returns: pd.DataFrame, width: int = 700, height: int = 350) -> str:
    """Return a base64-encoded PNG of the cumulative-return chart.

    cum_returns must have columns portfolio, btc, eth and a date index.
    """
    dpi = 96
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    if cum_returns.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    else:
        dates = pd.to_datetime(cum_returns.index)
        for col in ("portfolio", "btc", "eth"):
            if col in cum_returns.columns:
                ax.plot(
                    dates,
                    cum_returns[col] * 100,
                    label=_LABELS[col],
                    color=_COLORS[col],
                    linewidth=2.0 if col == "portfolio" else 1.4,
                    zorder=3 if col == "portfolio" else 2,
                )

        ax.axhline(0, color="#94a3b8", linewidth=0.8, linestyle="--", zorder=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.1f}%"))
        ax.tick_params(axis="y", labelsize=8)
        ax.set_ylabel("Cumulative return", fontsize=9)
        ax.legend(fontsize=9, framealpha=0.9)
        ax.grid(axis="y", color="#e2e8f0", linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout(pad=1.2)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()
