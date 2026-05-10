# binformer

Generates HTML performance reports for Binance spot trading accounts. Calculates Time-Weighted Return, compares against BTC and ETH benchmarks, and can deliver reports by email.

## What it produces

- KPI strip: current portfolio value, gross P&L, TWR %, net deposits
- Current holdings table: per-coin value and day-over-day change
- Period performance table: Since Inception, YTD, MTD, Last day, L7d, L14d, L1M, L3M, L6M, L1Y — strategy vs BTC and ETH
- Portfolio value chart: absolute USDT value of strategy vs hypothetical BTC-only and ETH-only accounts
- Cumulative return chart: normalised % return from inception for all three
- Output options: stdout, file, or email via SparkPost

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Binance account with API access (read-only permissions are sufficient)
- SparkPost account (only if sending email)

## Setup

```bash
git clone https://github.com/valeonte/binformer
cd binformer
uv sync
cp .env.example .env
# fill in .env with your credentials
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `BINANCE_API_KEY` | Yes | Binance read-only API key |
| `BINANCE_API_SECRET` | Yes | Binance API secret |
| `SPARKPOST_API_KEY` | Email only | SparkPost API key |
| `SPARKPOST_FROM_EMAIL` | Email only | Verified sender address |

## Usage

```bash
# Print HTML to stdout
uv run binformer

# Save to file
uv run binformer -o report.html

# Send by email
uv run binformer --to you@example.com

# Multiple recipients and custom subject
uv run binformer --to you@example.com,other@example.com --subject "Weekly report"

# Custom start date and initial balance
uv run binformer --start 2026-01-01 --starting-balance 500 -o report.html

# Separate live and test data (never cross-contaminate)
uv run binformer --data-dir live_data -o report.html
uv run binformer --data-dir test_data --refresh -o report_test.html
```

`--to` and `-o` can be combined. If neither is given, HTML goes to stdout.

### CLI options

| Option | Default | Description |
|---|---|---|
| `--start` | inception date | Start date for performance calculations (YYYY-MM-DD) |
| `--starting-balance` | `0.0` | Initial USDT balance (overrides snapshot-based init) |
| `--extra-symbols` | _(none)_ | Comma-separated symbols to always track, e.g. `ALGOUSDT,GASUSDT` |
| `--data-dir` | `user_data` | Directory for cached API data (trades, balances, metadata) |
| `--refresh` | `false` | Ignore cached history and refetch everything from Binance |
| `-o / --output` | _(none)_ | Write HTML report to this file |
| `--to` | _(none)_ | Comma-separated recipients — triggers SparkPost delivery |
| `--subject` | auto | Email subject line |

## Development

```bash
uv run pytest -v          # tests
uv run ruff check .       # lint
uv run ruff format .      # format
uv run ty check           # type check
```

CI runs all three on every push via GitHub Actions.

## License

MIT
