"""Thin Backtrader strategy adapter for forecast-driven signals."""

from __future__ import annotations

from datetime import UTC, datetime

try:
    import backtrader as bt
except ImportError:  # pragma: no cover - optional dependency.
    bt = None

from capm.domains.prediction import SignalDecision


def _as_backtrader_timestamp(value: datetime) -> datetime:
    normalized = value.astimezone(UTC)
    return normalized.replace(tzinfo=None)


def build_signal_map(signals: tuple[SignalDecision, ...]) -> dict[datetime, str]:
    """Convert signal decisions into a Backtrader-friendly timestamp map."""
    return {
        _as_backtrader_timestamp(signal.prediction_time): signal.action
        for signal in signals
    }


if bt is not None:  # pragma: no branch - exercised only when dependency is installed.

    class PredictionSignalStrategy(bt.Strategy):
        """Applies deterministic buy/sell/hold actions from forecast signals."""

        params = (("signal_map", {}),)

        def __init__(self) -> None:
            self.equity_curve: list[float] = []
            self.trade_pnls: list[float] = []

        def next(self) -> None:
            open_time = bt.num2date(self.data.datetime[0]).replace(tzinfo=None)
            action = self.params.signal_map.get(open_time)
            if action == "buy" and not self.position:
                self.buy()
            elif action == "sell" and self.position:
                self.close()
            self.equity_curve.append(float(self.broker.getvalue()))

        def notify_trade(self, trade: bt.Trade) -> None:
            if trade.isclosed:
                self.trade_pnls.append(float(trade.pnlcomm))

else:

    class PredictionSignalStrategy:  # pragma: no cover - dependency fallback.
        """Dependency-free placeholder used when Backtrader is unavailable."""

        pass
