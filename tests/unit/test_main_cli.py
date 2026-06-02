"""Unit tests for explicit Spot Demo CLI safety checks."""

from __future__ import annotations

import importlib
import unittest
from unittest.mock import patch

main_module = importlib.import_module("capm.main")


class MainCLITests(unittest.TestCase):
    """Exercise parser-level Spot Demo smoke-test safeguards."""

    def test_test_market_buy_requires_confirm_before_adapter_creation(self) -> None:
        with patch(
            "sys.argv",
            ["capm", "spot-demo", "test-market-buy", "--symbol", "BTCUSDT", "--usdt-amount", "10"],
        ):
            with patch("capm.main.BinanceSpotDemoTradingAdapter") as adapter:
                with self.assertRaises(SystemExit):
                    main_module.main()
        adapter.assert_not_called()

    def test_test_market_buy_rejects_non_positive_amount(self) -> None:
        with patch(
            "sys.argv",
            ["capm", "spot-demo", "test-market-buy", "--symbol", "BTCUSDT", "--usdt-amount", "0", "--confirm"],
        ):
            with patch("capm.main.BinanceSpotDemoTradingAdapter") as adapter:
                with self.assertRaises(SystemExit):
                    main_module.main()
        adapter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
