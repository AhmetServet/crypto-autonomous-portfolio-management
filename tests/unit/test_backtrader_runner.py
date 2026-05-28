"""Unit tests for backtesting helper functions."""

from __future__ import annotations

import unittest

from capm.domains.prediction import BacktestConfigurationError
from capm.services.backtesting.backtrader_runner import BacktraderBacktestRunner, _period_returns


class BacktraderRunnerHelperTests(unittest.TestCase):
    """Exercise pure helper logic used by the backtest runner."""

    def test_period_returns_handles_offset_equity_curve_lengths(self) -> None:
        returns = _period_returns((100.0, 105.0, 102.0))

        self.assertEqual(returns, (0.05, -0.02857142857142857))

    def test_period_returns_returns_empty_for_single_point_curve(self) -> None:
        self.assertEqual(_period_returns((100.0,)), ())

    def test_backtest_rejects_invalid_cash_fraction(self) -> None:
        runner = BacktraderBacktestRunner(market_data_repository=object())

        with self.assertRaises(BacktestConfigurationError):
            runner.run_from_forecast_result(
                symbol="BTCUSDT",
                interval="1m",
                start_time=None,
                end_time=None,
                forecast_result=object(),
                cash_fraction=0,
            )


if __name__ == "__main__":
    unittest.main()
