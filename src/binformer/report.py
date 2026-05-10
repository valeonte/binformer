"""Build the HTML performance report."""

from __future__ import annotations

from datetime import datetime

from jinja2 import BaseLoader, Environment

from binformer.performance import HoldingRow, MoneyMetrics, PeriodResult

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bot Performance — {{ metrics.report_date.strftime('%d %b %Y') }}</title>
<style>
  body { margin:0; padding:0; background:#f1f5f9; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; color:#1e293b; }
  .wrapper { max-width:660px; margin:24px auto; }
  .card { background:#fff; border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.08); margin-bottom:16px; }
  /* Header */
  .header { background:#0f172a; padding:28px 32px; }
  .header h1 { color:#f8fafc; margin:0; font-size:22px; font-weight:700; letter-spacing:-.3px; }
  .header p  { color:#94a3b8; margin:4px 0 0; font-size:13px; }
  /* KPI strip */
  .kpis { display:flex; flex-wrap:wrap; padding:20px 24px 8px; gap:12px; }
  .kpi { flex:1; min-width:130px; background:#f8fafc; border-radius:8px; padding:14px 16px; }
  .kpi-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }
  .kpi-value { font-size:20px; font-weight:700; }
  /* Tables */
  .section-title { font-size:13px; font-weight:600; color:#64748b; text-transform:uppercase;
                   letter-spacing:.5px; padding:20px 24px 8px; }
  table { width:100%; border-collapse:collapse; }
  th { background:#f8fafc; color:#64748b; font-size:11px; text-transform:uppercase;
       letter-spacing:.5px; padding:9px 16px; text-align:right; }
  th:first-child { text-align:left; }
  td { padding:9px 16px; font-size:13px; border-top:1px solid #f1f5f9; text-align:right; }
  td:first-child { text-align:left; font-weight:500; }
  .money-label { color:#64748b; }
  /* Performance colours */
  .pos { color:#16a34a; font-weight:600; }
  .neg { color:#dc2626; font-weight:600; }
  .na  { color:#94a3b8; }
  /* Holdings total row */
  .holdings-total td { border-top:2px solid #e2e8f0 !important; }
  /* Chart */
  .chart-wrap { padding:8px 16px 20px; }
  .chart-wrap img { width:100%; border-radius:6px; }
  /* Footer */
  .footer { text-align:center; color:#94a3b8; font-size:11px; padding:16px; }
</style>
</head>
<body>
<div class="wrapper">

<!-- Header -->
<div class="card">
  <div class="header">
    <h1>Binance Spot Bot &mdash; Performance Report</h1>
    <p>Generated {{ generated_at.strftime('%A, %d %B %Y %H:%M:%S') }} &nbsp;&bull;&nbsp; Inception {{ metrics.inception_date.strftime('%d %b %Y') }} &nbsp;&bull;&nbsp; Day {{ metrics.days_live }}</p>
  </div>

  <!-- KPI strip -->
  <div class="kpis">
    <div class="kpi">
      <div class="kpi-label">Current Value</div>
      <div class="kpi-value">${{ '%.2f'|format(metrics.current_value_usdt) }}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Gross PnL</div>
      <div class="kpi-value {{ 'pos' if metrics.gross_pnl_usdt >= 0 else 'neg' }}">
        {{ '+' if metrics.gross_pnl_usdt >= 0 else '' }}${{ '%.2f'|format(metrics.gross_pnl_usdt) }}
      </div>
    </div>
    <div class="kpi">
      <div class="kpi-label">TWR (inception)</div>
      <div class="kpi-value {{ 'pos' if metrics.twr_pct >= 0 else 'neg' }}">
        {{ '+' if metrics.twr_pct >= 0 else '' }}{{ '%.2f'|format(metrics.twr_pct) }}%
      </div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Net Deposits</div>
      <div class="kpi-value">${{ '%.2f'|format(metrics.net_deposits_usdt) }}</div>
    </div>
  </div>

  <!-- Money metrics table -->
  <div class="section-title">Account Summary</div>
  <table>
    <tr><td class="money-label">Starting value ({{ metrics.inception_date.strftime('%d %b %Y') }})</td><td>${{ '%.2f'|format(metrics.start_value_usdt) }}</td></tr>
    <tr><td class="money-label">Total deposits</td><td>${{ '%.2f'|format(metrics.total_deposits_usdt) }}</td></tr>
    <tr><td class="money-label">Total withdrawals</td><td>${{ '%.2f'|format(metrics.total_withdrawals_usdt) }}</td></tr>
    <tr><td class="money-label">Net deposits</td><td>${{ '%.2f'|format(metrics.net_deposits_usdt) }}</td></tr>
    <tr><td class="money-label">Current value</td><td><strong>${{ '%.2f'|format(metrics.current_value_usdt) }}</strong></td></tr>
    <tr><td class="money-label">Gross PnL (trading only)</td>
        <td class="{{ 'pos' if metrics.gross_pnl_usdt >= 0 else 'neg' }}">
          {{ '+' if metrics.gross_pnl_usdt >= 0 else '' }}${{ '%.2f'|format(metrics.gross_pnl_usdt) }}
        </td>
    </tr>
    <tr><td class="money-label">Time-Weighted Return</td>
        <td class="{{ 'pos' if metrics.twr_pct >= 0 else 'neg' }}">
          {{ '+' if metrics.twr_pct >= 0 else '' }}{{ '%.2f'|format(metrics.twr_pct) }}%
        </td>
    </tr>
  </table>
</div>

<!-- Current Holdings -->
{% if holdings %}
<div class="card">
  <div class="section-title">Current Holdings &ndash; {{ metrics.report_date.strftime('%d %b %Y') }}</div>
  <table>
    <thead>
      <tr>
        <th>Asset</th>
        <th>Amount</th>
        <th>Price</th>
        <th>Value</th>
        <th>vs Prev Day</th>
      </tr>
    </thead>
    <tbody>
      {% for h in holdings %}
      <tr>
        <td>{{ h.coin }}</td>
        <td>{{ fmt_amount(h.amount) }}</td>
        <td>{{ fmt_price(h.price) }}</td>
        <td>${{ '%.2f'|format(h.usdt_value) }}</td>
        <td>{{ fmt_change(h.change_usdt, h.change_pct) }}</td>
      </tr>
      {% endfor %}
      <tr class="holdings-total">
        <td colspan="3"><strong>Total</strong></td>
        <td><strong>${{ '%.2f'|format(holdings_total) }}</strong></td>
        <td>{{ fmt_change(holdings_change_usdt, holdings_change_pct) }}</td>
      </tr>
    </tbody>
  </table>
</div>
{% endif %}

<!-- Performance comparison -->
<div class="card">
  <div class="section-title">Period Performance vs Benchmarks</div>
  <table>
    <thead>
      <tr>
        <th>Period</th>
        <th>Strategy</th>
        <th>BTC</th>
        <th>ETH</th>
      </tr>
    </thead>
    <tbody>
      {% for row in periods %}
      <tr>
        <td>{{ row.label }}</td>
        <td>{{ fmt_pct(row.strategy) }}</td>
        <td>{{ fmt_pct(row.btc) }}</td>
        <td>{{ fmt_pct(row.eth) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<!-- Absolute value chart -->
{% if chart2_src %}
<div class="card">
  <div class="section-title">Trading PnL vs Benchmarks (USDT)</div>
  <div class="chart-wrap">
    <img src="{{ chart2_src }}" alt="Portfolio value chart">
  </div>
</div>
{% endif %}

<!-- Normalised returns chart -->
<div class="card">
  <div class="section-title">Normalised Cumulative Return</div>
  <div class="chart-wrap">
    <img src="{{ chart_src }}" alt="Cumulative return chart">
  </div>
</div>

<div class="footer">
  All figures in USDT &bull; Performance excludes deposits &amp; withdrawals (time-weighted return) &bull;
  Benchmarks: simple price return &bull; Not financial advice
</div>

</div>
</body>
</html>
"""


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return '<span class="na">&mdash;</span>'
    sign = "+" if value >= 0 else ""
    cls = "pos" if value >= 0 else "neg"
    return f'<span class="{cls}">{sign}{value * 100:.2f}%</span>'


def _fmt_amount(amount: float) -> str:
    if abs(amount) >= 100:
        return f"{amount:.2f}"
    if abs(amount) >= 1:
        return f"{amount:.4f}"
    return f"{amount:.6f}"


def _fmt_price(price: float | None) -> str:
    if price is None:
        return "&mdash;"
    if price >= 1000:
        return f"${price:,.2f}"
    if price >= 1:
        return f"${price:.4f}"
    return f"${price:.6f}"


def _fmt_change(change_usdt: float | None, change_pct: float | None) -> str:
    if change_usdt is None:
        return '<span class="na">&mdash;</span>'
    sign = "+" if change_usdt >= 0 else ""
    cls = "pos" if change_usdt >= 0 else "neg"
    pct_str = f" ({sign}{change_pct:.1f}%)" if change_pct is not None else ""
    return f'<span class="{cls}">{sign}${change_usdt:.2f}{pct_str}</span>'


def build_html_report(
    metrics: MoneyMetrics,
    periods: list[PeriodResult],
    holdings: list[HoldingRow],
    chart_b64: str,
    chart2_b64: str = "",
    generated_at: datetime | None = None,
    *,
    chart_cid: str | None = None,
    chart2_cid: str | None = None,
) -> str:
    chart_src = f"cid:{chart_cid}" if chart_cid else f"data:image/png;base64,{chart_b64}"
    if chart2_b64:
        chart2_src = f"cid:{chart2_cid}" if chart2_cid else f"data:image/png;base64,{chart2_b64}"
    else:
        chart2_src = ""

    holdings_total = sum(h.usdt_value for h in holdings)
    changes = [h.change_usdt for h in holdings if h.change_usdt is not None]
    if changes:
        holdings_change_usdt: float | None = sum(changes)
        prev_total = holdings_total - holdings_change_usdt
        holdings_change_pct: float | None = (
            holdings_change_usdt / prev_total * 100 if abs(prev_total) > 1e-10 else None
        )
    else:
        holdings_change_usdt = None
        holdings_change_pct = None

    env = Environment(loader=BaseLoader(), autoescape=False)
    tmpl = env.from_string(_TEMPLATE)
    return tmpl.render(
        metrics=metrics,
        periods=periods,
        holdings=holdings,
        holdings_total=holdings_total,
        holdings_change_usdt=holdings_change_usdt,
        holdings_change_pct=holdings_change_pct,
        chart_src=chart_src,
        chart2_src=chart2_src,
        fmt_pct=_fmt_pct,
        fmt_amount=_fmt_amount,
        fmt_price=_fmt_price,
        fmt_change=_fmt_change,
        generated_at=generated_at or datetime.now(),
    )
