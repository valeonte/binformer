# binformer — Claude context

Binance spot-bot performance reporter CLI. Fetches Binance account data, calculates Time-Weighted Return, and renders an HTML report comparing the strategy against BTC and ETH benchmarks. Can email via SparkPost.

## Architecture

```
src/binformer/
  cli.py          — click entry point; orchestrates the pipeline
  binance.py      — REST client (HMAC-SHA256 signed); snapshots, deposits, withdrawals, klines
  performance.py  — TWR calc, USDT conversion, period table, holdings, hypothetical benchmarks
  chart.py        — matplotlib charts → base64 PNG (normalised returns + absolute value)
  report.py       — Jinja2 HTML report
  mailer.py       — SparkPost REST send (no SDK); inline images via CID for Gmail compatibility
  storage.py      — Storage class: file-backed cache rooted at a configurable directory
  timeline.py     — reconstructs daily coin balances from deposits + trades + snapshots
tests/            — pytest + pytest-mock
.github/workflows/ci.yml — lint (ruff), type check (ty), tests (pytest)
```

## Key design decisions

- **TWR** for strategy — eliminates distortion from deposits/withdrawals
- **Simple price return** for BTC/ETH benchmarks
- Portfolio value reconstructed from daily coin balances × closing prices (not from snapshots)
- `--to` → SparkPost send; `-o` → write file; both together → send + write; neither → stdout
- Gmail chart fix: email uses CID inline images (`cid:chart.png`); file/stdout uses data URIs
- `--data-dir` controls where cached data lives — use separate dirs for live vs test data
- Periods: Since Inception, YTD (if applicable), MTD, Last day, L7d, L14d + monthly rows only when enough data exists (omitted rather than shown as `—`)
- Two charts: (1) absolute USDT value of strategy vs BTC-only vs ETH-only hypothetical accounts; (2) normalised % return from inception

## Storage (`storage.py`)

`Storage(root)` is instantiated in `cli.py` with the value of `--data-dir` (default `"user_data"`).
Module-level `merge_trades / merge_deposits / merge_withdrawals` are pure functions (no I/O).

```
<data-dir>/
  metadata.json       — last_updated, symbols, start_date, starting_balance_usdt
  deposits.json       — list of deposit records
  withdrawals.json    — list of withdrawal records
  balances.json       — reconstructed daily coin balances (date → {coin: amount})
  trades/
    BTCUSDT.json      — trade list per symbol
    ...
```

## CLI options

```
--start             YYYY-MM-DD start date (default: inception constant)
--starting-balance  initial USDT balance overriding snapshot-based init
--extra-symbols     comma-separated symbols to always track (e.g. ALGOUSDT,GASUSDT)
--data-dir          cache directory (default: user_data); use different dirs for live/test
--refresh           ignore cache and refetch all data from Binance
-o / --output       write HTML to file
--to                comma-separated email recipients (triggers SparkPost)
--subject           email subject
```

## Development workflow

```bash
uv sync                   # install deps
uv run binformer          # run CLI (needs .env loaded)
uv run pytest -v          # tests
uv run ruff check .       # lint
uv run ruff format .      # format
uv run ty check           # type check
```

Load env before running: `export $(cat .env | xargs)` or use a tool like direnv.

## Conventions

- src-layout: all source under `src/binformer/`
- `uv` for all package operations — never pip
- Line length 100 (ruff); long lines in `report.py` and tests are ignored
- No SDK for Binance or SparkPost — raw `requests`
- Python 3.11+

## Keeping this file up to date

Update this file whenever: new modules are added, the CLI interface changes, key design decisions are revised, or dependencies change.
