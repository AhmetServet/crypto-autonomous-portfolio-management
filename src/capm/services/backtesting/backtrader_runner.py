"""Backtrader-based offline portfolio evaluation for forecast outputs."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

try:
    import backtrader as bt
except ImportError:  # pragma: no cover - optional dependency.
    bt = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional dependency.
    pd = None

from capm.core.contracts import MarketDataRepositoryPort
from capm.domains.prediction import (
    BacktestConfigurationError,
    BacktestReport,
    ForecastResult,
    MissingOptionalDependencyError,
    ThresholdSignalPolicy,
    generate_threshold_signals,
)

from .strategy_adapter import PredictionSignalStrategy, build_signal_map


def _max_drawdown(equity_curve: tuple[float, ...]) -> float:
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak == 0:
            continue
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    return max_drawdown


def _period_returns(equity_curve: tuple[float, ...]) -> tuple[float, ...]:
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous == 0:
            continue
        returns.append((current - previous) / previous)
    return tuple(returns)


def _sharpe_ratio(returns: tuple[float, ...]) -> float:
    if not returns:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
    std_dev = sqrt(variance)
    if std_dev == 0:
        return 0.0
    return mean_return / std_dev


def _sortino_ratio(returns: tuple[float, ...]) -> float:
    if not returns:
        return 0.0
    mean_return = sum(returns) / len(returns)
    downside_returns = tuple(value for value in returns if value < 0)
    if not downside_returns:
        return 0.0
    downside_variance = sum(value**2 for value in downside_returns) / len(downside_returns)
    downside_std_dev = sqrt(downside_variance)
    if downside_std_dev == 0:
        return 0.0
    return mean_return / downside_std_dev


def _profit_factor(trade_pnls: tuple[float, ...]) -> float:
    gross_profit = sum(value for value in trade_pnls if value > 0)
    gross_loss = abs(sum(value for value in trade_pnls if value < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


@dataclass(slots=True)
class BacktraderBacktestRunner:
    """Runs a deterministic Backtrader simulation over stored candles."""

    market_data_repository: MarketDataRepositoryPort

    def run_from_forecast_result(
        self,
        *,
        symbol: str,
        interval: str,
        start_time,
        end_time,
        forecast_result: ForecastResult,
        starting_cash: float = 10_000.0,
        signal_policy: ThresholdSignalPolicy | None = None,
        commission_rate: float = 0.001,
        cash_fraction: float = 0.95,
    ) -> BacktestReport:
        """Evaluate one forecast result against stored historical candles."""
        if bt is None or pd is None:
            raise MissingOptionalDependencyError(
                "Backtesting requires the optional `backtest` dependencies (`backtrader` and `pandas`)."
            )
        if starting_cash <= 0:
            raise BacktestConfigurationError("`starting_cash` must be positive.")
        if commission_rate < 0:
            raise BacktestConfigurationError("`commission_rate` must not be negative.")
        if not 0 < cash_fraction <= 1:
            raise BacktestConfigurationError("`cash_fraction` must be in the interval (0, 1].")

        candles = self.market_data_repository.get_candles(symbol, interval, start_time, end_time)
        if not candles:
            raise BacktestConfigurationError("No stored candles were available for the requested backtest window.")

        signals = generate_threshold_signals(
            forecast_result,
            policy=signal_policy,
        )
        frame = pd.DataFrame(
            {
                "open": [float(candle.open) for candle in candles],
                "high": [float(candle.high) for candle in candles],
                "low": [float(candle.low) for candle in candles],
                "close": [float(candle.close) for candle in candles],
                "volume": [float(candle.volume) for candle in candles],
            },
            index=pd.DatetimeIndex([candle.open_time for candle in candles]).tz_localize(None),
        )

        cerebro = bt.Cerebro()
        cerebro.adddata(bt.feeds.PandasData(dataname=frame))
        cerebro.addstrategy(
            PredictionSignalStrategy,
            signal_map=build_signal_map(signals),
            cash_fraction=cash_fraction,
        )
        cerebro.broker.setcash(starting_cash)
        cerebro.broker.setcommission(commission=commission_rate)
        results = cerebro.run()
        strategy = results[0]

        equity_curve = tuple(strategy.equity_curve) or (starting_cash, float(cerebro.broker.getvalue()))
        trade_pnls = tuple(strategy.trade_pnls)
        final_value = float(cerebro.broker.getvalue())
        step_returns = _period_returns(equity_curve)

        notes = (
            f"Commission rate: {commission_rate:.6f}.",
            "Slippage excluded in v1.",
            f"Buy signals deploy {cash_fraction:.2%} of available cash.",
            "Sharpe and Sortino ratios are computed from step returns without annualization.",
        )
        return BacktestReport(
            symbol=symbol,
            interval=interval,
            model_name=forecast_result.model_name,
            trade_count=len(trade_pnls),
            profit_factor=_profit_factor(trade_pnls),
            max_drawdown=_max_drawdown(equity_curve),
            sharpe_ratio=_sharpe_ratio(step_returns),
            sortino_ratio=_sortino_ratio(step_returns),
            cumulative_return=(final_value / starting_cash) - 1,
            buy_and_hold_return=(float(candles[-1].close) / float(candles[0].close)) - 1,
            notes=notes,
        )
