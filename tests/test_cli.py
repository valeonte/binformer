"""Integration tests for the CLI."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from click.testing import CliRunner
from pytest_mock import MockerFixture

from binformer.cli import main

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_snapshots() -> pd.DataFrame:
    dates = pd.date_range("2026-04-06", periods=5, freq="D").date
    return pd.DataFrame(
        {"total_btc": [0.125] * 5},
        index=pd.Index(dates, name="date"),
    )


def _make_prices(start: float, step: float) -> pd.Series:
    dates = pd.date_range("2026-04-06", periods=5, freq="D").date
    return pd.Series(
        [start + i * step for i in range(5)],
        index=pd.Index(dates, name="date"),
        name="close",
    )


def _patch_client(mocker: MockerFixture) -> None:
    mock_cls = mocker.patch("binformer.cli.BinanceClient")
    instance = mock_cls.return_value
    instance.get_account_snapshots.return_value = _make_snapshots()
    instance.get_deposits.return_value = pd.DataFrame(columns=["date", "coin", "amount"])
    instance.get_withdrawals.return_value = pd.DataFrame(columns=["date", "coin", "amount"])
    instance.get_klines.side_effect = lambda sym, _start: (
        _make_prices(80_000, 500) if "BTC" in sym else _make_prices(2_000, 20)
    )


def _base_env() -> dict[str, str]:
    return {
        "BINANCE_API_KEY": "testkey",
        "BINANCE_API_SECRET": "testsecret",
    }


# ── tests ─────────────────────────────────────────────────────────────────────


class TestCLIOutputFile:
    def test_writes_html_to_file(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        out = tmp_path / "report.html"
        runner = CliRunner()
        result = runner.invoke(main, ["--output", str(out)], env=_base_env())
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content

    def test_missing_api_key_exits_nonzero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        out = tmp_path / "r.html"
        result = runner.invoke(main, ["--output", str(out)], env={})
        assert result.exit_code != 0

    def test_no_output_no_email_prints_to_stdout(self, mocker: MockerFixture) -> None:
        _patch_client(mocker)
        runner = CliRunner()
        result = runner.invoke(main, [], env=_base_env())
        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.output


class TestCLIEmail:
    def test_sends_email_when_to_provided(self, mocker: MockerFixture) -> None:
        _patch_client(mocker)
        mock_send = mocker.patch("binformer.cli.send_email")
        env = {
            **_base_env(),
            "SPARKPOST_API_KEY": "sp_key",
            "SPARKPOST_FROM_EMAIL": "bot@example.com",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["--to", "alice@example.com,bob@example.com"], env=env)
        assert result.exit_code == 0, result.output
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to"] == ["alice@example.com", "bob@example.com"]
        assert call_kwargs["from_email"] == "bot@example.com"

    def test_sparkpost_key_required_when_to_given(self, mocker: MockerFixture) -> None:
        _patch_client(mocker)
        runner = CliRunner()
        result = runner.invoke(main, ["--to", "x@example.com"], env=_base_env())
        assert result.exit_code != 0

    def test_both_output_and_email(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        mock_send = mocker.patch("binformer.cli.send_email")
        out = tmp_path / "r.html"
        env = {
            **_base_env(),
            "SPARKPOST_API_KEY": "sp_key",
            "SPARKPOST_FROM_EMAIL": "bot@example.com",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["--output", str(out), "--to", "x@example.com"], env=env)
        assert result.exit_code == 0
        assert out.exists()
        mock_send.assert_called_once()


class TestCLICustomStartDate:
    def test_custom_start_date_accepted(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        out = tmp_path / "r.html"
        runner = CliRunner()
        result = runner.invoke(
            main, ["--output", str(out), "--start", "2026-04-06"], env=_base_env()
        )
        assert result.exit_code == 0
