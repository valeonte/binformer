"""CLI entry point for binformer."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

import click

from binformer.binance import INCEPTION_DATE, BinanceClient
from binformer.chart import build_chart
from binformer.mailer import send_email
from binformer.performance import (
    build_performance_table,
    cash_flows_to_usdt,
    compute_money_metrics,
    cumulative_returns,
    snapshots_to_usdt,
)
from binformer.report import build_html_report


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise click.ClickException(f"Environment variable {name} is not set.")
    return val


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
def main(
    recipients: str | None,
    output_path: str | None,
    subject: str | None,
    start_date: str,
) -> None:
    """Generate a Binance spot-bot performance report."""
    inception = datetime.strptime(start_date, "%Y-%m-%d").date()

    api_key = _require_env("BINANCE_API_KEY")
    api_secret = _require_env("BINANCE_API_SECRET")

    if recipients:
        sp_key = _require_env("SPARKPOST_API_KEY")
        from_email = _require_env("SPARKPOST_FROM_EMAIL")
    else:
        sp_key = from_email = ""

    click.echo("Fetching Binance data…")
    client = BinanceClient(api_key, api_secret)

    snapshots = client.get_account_snapshots(inception)
    deposits_df = client.get_deposits(inception)
    withdrawals_df = client.get_withdrawals(inception)
    btc_prices = client.get_klines("BTCUSDT", inception)
    eth_prices = client.get_klines("ETHUSDT", inception)

    if snapshots.empty:
        raise click.ClickException("No account snapshots returned — check API key permissions.")

    net_cf = cash_flows_to_usdt(deposits_df, withdrawals_df, btc_prices, eth_prices)
    usdt_values = snapshots_to_usdt(snapshots, btc_prices)

    dep_total = float(net_cf[net_cf > 0].sum()) if not net_cf.empty else 0.0
    wd_total = float(abs(net_cf[net_cf < 0].sum())) if not net_cf.empty else 0.0

    metrics = compute_money_metrics(usdt_values, net_cf, dep_total, wd_total, inception)
    periods = build_performance_table(usdt_values, net_cf, btc_prices, eth_prices, inception)
    cum = cumulative_returns(usdt_values, net_cf, btc_prices, eth_prices)
    chart_b64 = build_chart(cum)
    html = build_html_report(metrics, periods, chart_b64)

    report_date = date.today().strftime("%d %b %Y")
    if subject is None:
        subject = f"Bot Performance Report – {report_date}"

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
        click.echo(f"Report written to {output_path}")

    if recipients:
        to_list = [r.strip() for r in recipients.split(",") if r.strip()]
        click.echo(f"Sending to {to_list}…")
        send_email(
            api_key=sp_key,
            from_email=from_email,
            to=to_list,
            subject=subject,
            html=html,
        )
        click.echo("Email sent.")

    if not output_path and not recipients:
        sys.stdout.write(html)
