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
    instance.snapshot_coin_balances = {}
    instance.get_trade_symbols.return_value = []


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
        result = runner.invoke(
            main, ["--output", str(out), "--data-dir", str(tmp_path / "data")], env=_base_env()
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content

    def test_missing_api_key_exits_nonzero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        out = tmp_path / "r.html"
        result = runner.invoke(main, ["--output", str(out)], env={})
        assert result.exit_code != 0

    def test_no_output_no_email_prints_to_stdout(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        runner = CliRunner()
        result = runner.invoke(main, ["--data-dir", str(tmp_path / "data")], env=_base_env())
        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.output


class TestCLIEmail:
    def test_sends_email_when_to_provided(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        mock_send = mocker.patch("binformer.cli.send_email")
        env = {
            **_base_env(),
            "SPARKPOST_API_KEY": "sp_key",
            "SPARKPOST_FROM_EMAIL": "bot@example.com",
        }
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--to", "alice@example.com,bob@example.com", "--data-dir", str(tmp_path / "data")],
            env=env,
        )
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
        result = runner.invoke(
            main,
            ["--output", str(out), "--to", "x@example.com", "--data-dir", str(tmp_path / "data")],
            env=env,
        )
        assert result.exit_code == 0
        assert out.exists()
        mock_send.assert_called_once()

    def test_email_sends_inline_images(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        mock_send = mocker.patch("binformer.cli.send_email")
        env = {
            **_base_env(),
            "SPARKPOST_API_KEY": "sp_key",
            "SPARKPOST_FROM_EMAIL": "bot@example.com",
        }
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--to", "x@example.com", "--data-dir", str(tmp_path / "data")],
            env=env,
        )
        assert result.exit_code == 0, result.output
        call_kwargs = mock_send.call_args.kwargs
        images = call_kwargs.get("inline_images", [])
        names = {img["name"] for img in images}
        assert "chart.png" in names
        assert "chart2.png" in names


class TestCLICustomStartDate:
    def test_custom_start_date_accepted(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        out = tmp_path / "r.html"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--output", str(out), "--start", "2026-04-06", "--data-dir", str(tmp_path / "data")],
            env=_base_env(),
        )
        assert result.exit_code == 0


class TestCLIDataDir:
    def test_data_dir_writes_to_custom_location(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        data_dir = tmp_path / "my_live_data"
        runner = CliRunner()
        result = runner.invoke(
            main, ["--data-dir", str(data_dir)], env=_base_env()
        )
        assert result.exit_code == 0, result.output
        assert (data_dir / "metadata.json").exists()

    def test_two_data_dirs_are_independent(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_client(mocker)
        runner = CliRunner()
        dir_a = tmp_path / "live"
        dir_b = tmp_path / "test"
        for d in (dir_a, dir_b):
            result = runner.invoke(main, ["--data-dir", str(d)], env=_base_env())
            assert result.exit_code == 0, result.output
        assert (dir_a / "metadata.json").exists()
        assert (dir_b / "metadata.json").exists()
        assert dir_a != dir_b

    def test_default_is_user_data(self, mocker: MockerFixture) -> None:
        mock_storage_cls = mocker.patch("binformer.cli.storage.Storage")
        mock_storage_cls.return_value.load_metadata.return_value = {}
        _patch_client(mocker)
        runner = CliRunner()
        runner.invoke(main, [], env=_base_env())
        mock_storage_cls.assert_called_once_with("user_data")
