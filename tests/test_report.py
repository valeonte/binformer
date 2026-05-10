"""Tests for HTML report generation."""

from __future__ import annotations

from datetime import date

from binformer.performance import MoneyMetrics, PeriodResult
from binformer.report import build_html_report


def _sample_metrics() -> MoneyMetrics:
    return MoneyMetrics(
        inception_date=date(2026, 4, 6),
        report_date=date(2026, 5, 9),
        days_live=33,
        start_value_usdt=10_000.0,
        total_deposits_usdt=0.0,
        total_withdrawals_usdt=0.0,
        net_deposits_usdt=0.0,
        current_value_usdt=10_500.0,
        gross_pnl_usdt=500.0,
        twr_pct=5.0,
    )


def _sample_periods() -> list[PeriodResult]:
    return [
        PeriodResult("Since Inception", 0.05, 0.12, -0.03),
        PeriodResult("MTD", 0.02, 0.04, None),
        PeriodResult("Last 7 days", 0.007, 0.015, -0.002),
        PeriodResult("Last 3M", None, None, None),
    ]


class TestBuildHtmlReport:
    def test_returns_html_string(self) -> None:
        html = build_html_report(_sample_metrics(), _sample_periods(), "FAKE_B64==")
        assert isinstance(html, str)
        assert html.startswith("<!DOCTYPE html>")

    def test_contains_current_value(self) -> None:
        html = build_html_report(_sample_metrics(), _sample_periods(), "")
        assert "10500.00" in html

    def test_contains_all_period_labels(self) -> None:
        html = build_html_report(_sample_metrics(), _sample_periods(), "")
        for label in ("Since Inception", "MTD", "Last 7 days", "Last 3M"):
            assert label in html

    def test_na_rendered_for_none_periods(self) -> None:
        html = build_html_report(_sample_metrics(), _sample_periods(), "")
        assert "&mdash;" in html

    def test_positive_pnl_has_pos_class(self) -> None:
        html = build_html_report(_sample_metrics(), _sample_periods(), "")
        assert 'class="pos"' in html

    def test_negative_value_has_neg_class(self) -> None:
        metrics = _sample_metrics()
        metrics.gross_pnl_usdt = -200.0
        metrics.twr_pct = -2.0
        html = build_html_report(metrics, _sample_periods(), "")
        assert 'class="neg"' in html

    def test_chart_embedded_in_img_tag(self) -> None:
        html = build_html_report(_sample_metrics(), _sample_periods(), "TESTDATA==")
        assert "data:image/png;base64,TESTDATA==" in html
