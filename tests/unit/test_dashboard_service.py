"""Unit tests for dashboard report service payload derivation."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from capm.domains.trading import AgentDecisionJournalEntry
from capm.services.dashboard import DashboardReportService


class FakeDashboardRepository:
    """Repository double for dashboard service tests."""

    def __init__(self, entries):
        self.entries = entries

    def list_recent_agent_decision_journal_entries(self, symbol: str, interval: str, limit: int = 20):
        return self.entries[:limit]


class DashboardReportServiceTests(unittest.TestCase):
    """Exercise derived execution order payloads."""

    def test_orders_resolve_reconciled_order_payload_and_pnl(self) -> None:
        buy = AgentDecisionJournalEntry(
            id=1,
            cycle_id="cycle-buy",
            mode="spot-demo",
            symbol="BTCUSDT",
            interval="1m",
            reference_time=datetime(2026, 6, 1, tzinfo=UTC),
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            action="buy",
            risk_status="approved",
            execution_status="filled",
            reason="buy reason",
            exchange_order_id="101",
            exchange_client_order_id="client-buy",
            exchange_response={
                "submission": {
                    "orderId": 101,
                    "side": "BUY",
                    "status": "FILLED",
                    "type": "MARKET",
                    "executedQty": "1.0",
                    "cummulativeQuoteQty": "100.0",
                    "fills": [{"commission": "0.001", "commissionAsset": "BTC"}],
                }
            },
        )
        sell = AgentDecisionJournalEntry(
            id=2,
            cycle_id="cycle-sell",
            mode="spot-demo",
            symbol="BTCUSDT",
            interval="1m",
            reference_time=datetime(2026, 6, 2, tzinfo=UTC),
            created_at=datetime(2026, 6, 2, tzinfo=UTC),
            action="sell",
            risk_status="approved",
            execution_status="filled",
            reason="sell reason",
            exchange_order_id="102",
            exchange_client_order_id="client-sell",
            exchange_response={
                "reconciliation": {
                    "orderId": 102,
                    "side": "SELL",
                    "status": "FILLED",
                    "type": "MARKET",
                    "executedQty": "0.5",
                    "cummulativeQuoteQty": "60.0",
                    "fills": [{"commission": "0.06", "commissionAsset": "USDT"}],
                }
            },
        )
        service = DashboardReportService(FakeDashboardRepository((sell, buy)))

        payload = service.orders(symbol="BTCUSDT", interval="1m", limit=10)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(payload["orders"]), 2)
        latest = payload["orders"][0]
        self.assertEqual(latest["decision_journal_id"], 2)
        self.assertEqual(latest["exchange_order_id"], "102")
        self.assertEqual(latest["order_status"], "filled")
        self.assertEqual(latest["average_price"], 120.0)
        self.assertEqual(latest["realized_pnl_usdt"], 10.0)
        self.assertEqual(latest["realized_pnl_pct"], 0.2)
        self.assertEqual(latest["commission"], {"USDT": 0.06})


if __name__ == "__main__":
    unittest.main()
