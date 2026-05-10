# binformer

Generates HTML performance reports for Binance spot trading accounts. Calculates Time-Weighted Return, compares against BTC and ETH benchmarks, and can deliver reports by email.

## What it produces

- KPI strip: current portfolio value, gross P&L, TWR %, net deposits
- Period performance table: Since Inception, YTD, MTD, L7d, L30d, L1M, L3M, L6M, L1Y — strategy vs BTC and ETH
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

# Custom start date
uv run binformer --start 2026-01-01 -o report.html
```

`--to` and `-o` can be combined. If neither is given, HTML goes to stdout.

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
