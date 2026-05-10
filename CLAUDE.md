# binformer — Claude context

Binance spot-bot performance reporter CLI. Fetches Binance account data, calculates Time-Weighted Return, and renders an HTML report comparing the strategy against BTC and ETH benchmarks. Can email via SparkPost.

## Architecture

```
src/binformer/
  cli.py          — click entry point; orchestrates the pipeline
  binance.py      — REST client (HMAC-SHA256 signed); snapshots, deposits, withdrawals, klines
  performance.py  — TWR calc, USDT conversion, period table, cumulative returns
  chart.py        — matplotlib cumulative-return chart → base64 PNG
  report.py       — Jinja2 HTML report
  mailer.py       — SparkPost REST send (no SDK)
tests/            — pytest + pytest-mock
.github/workflows/ci.yml — lint (ruff), type check (ty), tests (pytest)
```

## Key design decisions

- **TWR** for strategy — eliminates distortion from deposits/withdrawals
- **Simple price return** for BTC/ETH benchmarks
- Portfolio value: `totalAssetOfBtc` (from snapshot) × daily BTC/USDT close price
- `--to` → SparkPost send; `-o` → write file; both together → send + write; neither → stdout
- Periods: Since Inception, YTD, MTD, L7d, L30d, L1M, L3M, L6M, L1Y; shows `—` when data insufficient
- Chart normalises all three series to 0% at inception date

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
