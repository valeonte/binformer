"""CLI entry point for binformer."""

from __future__ import annotations

import contextlib
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import click
import pandas as pd

from binformer import storage
from binformer.binance import INCEPTION_DATE, STABLECOINS, BinanceClient
from binformer.chart import build_absolute_chart, build_chart
from binformer.mailer import send_email
from binformer.performance import (
    build_holdings,
    build_performance_table,
    cash_flows_to_usdt,
    compute_money_metrics,
    cumulative_returns,
    hypothetical_coin_values,
    pnl_series,
    reconstructed_usdt_values,
)
from binformer.report import build_html_report
from binformer.timeline import print_account_timeline


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise click.ClickException(f"Environment variable {name} is not set.")
    return val


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return df.to_dict("records")


def _deposits_df(records: list[dict]) -> pd.DataFrame:
    cols = ["date", "time_ms", "coin", "amount", "source"]
    if not records:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(records)


def _withdrawals_df(records: list[dict]) -> pd.DataFrame:
    cols = ["date", "coin", "amount"]
    if not records:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(records)


@click.command()
@click.option(
    "--to",
    "recipients",
    default=None,
    help="Comma-separated recipient email addresses. Triggers SparkPost delivery.",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Write HTML report to this file.",
)
@click.option(
    "--subject",
    default=None,
    help="Email subject (default: 'Performance Report – <date>').",
)
@click.option(
    "--start",
    "start_date",
    default=str(INCEPTION_DATE),
    show_default=True,
    help="Start date for performance calculations (YYYY-MM-DD).",
)
@click.option(
    "--starting-balance",
    default=0.0,
    type=float,
    show_default=True,
    help="Initial USDT balance at start date (overrides snapshot-based init).",
)
@click.option(
    "--extra-symbols",
    default="",
    help="Additional trading symbols to always include, e.g. ALGOUSDT,GASUSDT.",
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Ignore saved history and refetch all data from Binance.",
)
@click.option(
    "--data-dir",
    default="user_data",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory for cached API data (trades, balances, metadata).",
)
def main(
    recipients: str | None,
    output_path: str | None,
    subject: str | None,
    start_date: str,
    starting_balance: float,
    extra_symbols: str,
    refresh: bool,
    data_dir: str,
) -> None:
    """Generate a Binance spot-bot performance report."""
    inception = datetime.strptime(start_date, "%Y-%m-%d").date()
    store = storage.Storage(data_dir)

    api_key = _require_env("BINANCE_API_KEY")
    api_secret = _require_env("BINANCE_API_SECRET")

    if recipients:
        sp_key = _require_env("SPARKPOST_API_KEY")
        from_email = _require_env("SPARKPOST_FROM_EMAIL")
    else:
        sp_key = from_email = ""

    extra_sym_list = [s.strip().upper() for s in extra_symbols.split(",") if s.strip()]

    meta = store.load_metadata()
    is_first_run = not meta or refresh
    cached_symbols: set[str] = set() if is_first_run else set(meta.get("symbols", []))

    click.echo("Fetching Binance data…")
    client = BinanceClient(api_key, api_secret)

    snapshots = client.get_account_snapshots(inception)
    btc_prices = client.get_klines("BTCUSDT", inception)
    eth_prices = client.get_klines("ETHUSDT", inception)

    if snapshots.empty:
        raise click.ClickException("No account snapshots returned — check API key permissions.")

    # ── Deposits ───────────────────────────────────────────────────────────
    if is_first_run:
        deposits_df = client.get_deposits(inception)
        store.save_deposits(_df_to_records(deposits_df))
    else:
        cached_deps = store.load_deposits()
        last_dep_ms = max((r["time_ms"] for r in cached_deps), default=0)
        if last_dep_ms:
            last_dep_date = datetime.fromtimestamp(last_dep_ms / 1000, tz=UTC).date()
            fetch_dep_from = max(inception, last_dep_date - timedelta(days=7))
        else:
            fetch_dep_from = inception
        fresh_df = client.get_deposits(fetch_dep_from)
        merged_deps = storage.merge_deposits(cached_deps, _df_to_records(fresh_df))
        store.save_deposits(merged_deps)
        deposits_df = _deposits_df(merged_deps)

    # ── Withdrawals ────────────────────────────────────────────────────────
    if is_first_run:
        withdrawals_df = client.get_withdrawals(inception)
        store.save_withdrawals(_df_to_records(withdrawals_df))
    else:
        cached_wds = store.load_withdrawals()
        last_wd_date = max((r["date"] for r in cached_wds), default=None)
        if last_wd_date:
            fetch_wd_from = max(inception, last_wd_date - timedelta(days=7))
        else:
            fetch_wd_from = inception
        fresh_wdf = client.get_withdrawals(fetch_wd_from)
        merged_wds = storage.merge_withdrawals(cached_wds, _df_to_records(fresh_wdf))
        store.save_withdrawals(merged_wds)
        withdrawals_df = _withdrawals_df(merged_wds)

    # ── Symbols ────────────────────────────────────────────────────────────
    if is_first_run:
        deposit_coins: set[str] = (
            set(deposits_df["coin"].unique()) - STABLECOINS if not deposits_df.empty else set()
        )
        all_symbols = sorted(set(client.get_trade_symbols(deposit_coins)) | set(extra_sym_list))
    else:
        all_symbols = sorted(cached_symbols | set(extra_sym_list))
    click.echo(f"Fetching trades for {all_symbols}…")

    # ── Snapshot coverage check ────────────────────────────────────────────
    tracked_coins = {sym.removesuffix("USDT") for sym in all_symbols} | STABLECOINS
    for snap_date, snap_coins in sorted(client.snapshot_coin_balances.items()):
        uncovered = sorted(
            coin for coin, amt in snap_coins.items()
            if coin not in tracked_coins and abs(amt) > 1e-8
        )
        if uncovered:
            suggestions = ", ".join(f"{c}USDT" for c in uncovered)
            raise click.ClickException(
                f"Snapshot {snap_date} contains untracked coin(s): {', '.join(uncovered)}. "
                f"Add --extra-symbols {suggestions}"
            )

    # ── Trades (per-symbol incremental) ────────────────────────────────────
    all_trades: list[dict] = []
    for sym in all_symbols:
        if is_first_run:
            fresh = client.get_trades([sym], inception)
            store.save_trades(sym, fresh)
            all_trades.extend(fresh)
        else:
            cached = store.load_trades(sym)
            if cached:
                last_ms = max(int(t["time"]) for t in cached)
                trade_fetch_from = max(
                    inception,
                    datetime.fromtimestamp(last_ms / 1000, tz=UTC).date() - timedelta(days=1),
                )
            else:
                trade_fetch_from = inception
            fresh = client.get_trades([sym], trade_fetch_from)
            merged = storage.merge_trades(cached, fresh)
            store.save_trades(sym, merged)
            all_trades.extend(merged)

    all_trades.sort(key=lambda t: int(t["time"]))

    # ── Prices ─────────────────────────────────────────────────────────────
    coin_prices: dict[str, pd.Series] = {"BTC": btc_prices, "ETH": eth_prices}
    for sym in all_symbols:
        if sym in ("BTCUSDT", "ETHUSDT"):
            continue
        coin = sym.removesuffix("USDT")
        with contextlib.suppress(Exception):
            coin_prices[coin] = client.get_klines(sym, inception)

    # ── Timeline ───────────────────────────────────────────────────────────
    saved_balances = {} if is_first_run else store.load_daily_balances()
    combined_snapshots = {**client.snapshot_coin_balances, **saved_balances}

    daily_balances = print_account_timeline(
        deposits_df,
        all_trades,
        coin_prices,
        combined_snapshots,
        starting_usdt=starting_balance,
        binance_snapshots=client.snapshot_coin_balances,
    )
    store.save_daily_balances(daily_balances)

    store.save_metadata({
        "last_updated": str(date.today()),
        "symbols": all_symbols,
        "start_date": str(inception),
        "starting_balance_usdt": starting_balance,
    })

    # ── Performance report ─────────────────────────────────────────────────
    net_cf = cash_flows_to_usdt(deposits_df, withdrawals_df, btc_prices, eth_prices)
    usdt_values = reconstructed_usdt_values(daily_balances, coin_prices)

    # Only count cash flows AFTER the initial date — flows on the initial date are
    # already embedded in usdt_values.iloc[0] (start_value) and must not be double-counted.
    usdt_start = usdt_values.index[0] if not usdt_values.empty else inception
    net_cf_after = net_cf[net_cf.index > usdt_start] if not net_cf.empty else net_cf

    dep_total = float(net_cf_after[net_cf_after > 0].sum()) if not net_cf_after.empty else 0.0
    wd_total = float(abs(net_cf_after[net_cf_after < 0].sum())) if not net_cf_after.empty else 0.0

    metrics = compute_money_metrics(usdt_values, net_cf, dep_total, wd_total, inception)
    periods = build_performance_table(usdt_values, net_cf, btc_prices, eth_prices, inception)
    holdings = build_holdings(daily_balances, coin_prices)
    btc_hyp = hypothetical_coin_values(usdt_values, net_cf_after, btc_prices)
    eth_hyp = hypothetical_coin_values(usdt_values, net_cf_after, eth_prices)
    cum = cumulative_returns(usdt_values, net_cf, btc_prices, eth_prices)
    chart_b64 = build_chart(cum)
    chart2_b64 = build_absolute_chart(
        pnl_series(usdt_values, net_cf_after),
        pnl_series(btc_hyp, net_cf_after),
        pnl_series(eth_hyp, net_cf_after),
    )
    generated_at = datetime.now(UTC)

    report_date = date.today().strftime("%d %b %Y")
    if subject is None:
        subject = f"Bot Performance Report – {report_date}"

    if output_path:
        html = build_html_report(
            metrics, periods, holdings, chart_b64, chart2_b64, generated_at=generated_at,
        )
        Path(output_path).write_text(html, encoding="utf-8")
        click.echo(f"Report written to {output_path}")

    if recipients:
        html_email = build_html_report(
            metrics, periods, holdings, chart_b64, chart2_b64,
            generated_at=generated_at, chart_cid="chart.png", chart2_cid="chart2.png",
        )
        to_list = [r.strip() for r in recipients.split(",") if r.strip()]
        click.echo(f"Sending to {to_list}…")
        send_email(
            api_key=sp_key,
            from_email=from_email,
            to=to_list,
            subject=subject,
            html=html_email,
            inline_images=[
                {"name": "chart.png", "type": "image/png", "data": chart_b64},
                {"name": "chart2.png", "type": "image/png", "data": chart2_b64},
            ],
        )
        click.echo("Email sent.")

    if not output_path and not recipients:
        html = build_html_report(
            metrics, periods, holdings, chart_b64, chart2_b64, generated_at=generated_at,
        )
        sys.stdout.write(html)


if __name__ == "__main__":
    main()
