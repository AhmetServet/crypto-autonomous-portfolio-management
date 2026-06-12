"""Contracts for trading-agent persistence and decision policies."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from capm.domains.trading import (
    AgentDecisionJournalEntry,
    AgentDecisionJournalSummary,
    DecisionRequest,
    ProposedDecision,
)


class AgentDecisionJournalRepositoryPort(Protocol):
    """Persists auditable trading-agent decisions."""

    def save_agent_decision_journal_entry(self, entry: AgentDecisionJournalEntry) -> AgentDecisionJournalEntry:
        """Insert or return one idempotent decision row."""

    def list_recent_agent_decision_journal_entries(
        self,
        symbol: str,
        interval: str,
        limit: int = 20,
    ) -> tuple[AgentDecisionJournalEntry, ...]:
        """Return recent agent decision rows for observability."""

    def get_agent_decision_journal_entry(self, journal_id: int) -> AgentDecisionJournalEntry | None:
        """Return one agent decision row by id."""

    def summarize_agent_decision_journal(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> AgentDecisionJournalSummary:
        """Return aggregate decision counts for one time range."""


class DecisionPolicyPort(Protocol):
    """Produces one proposed action from normalized cycle input."""

    def decide(self, request: DecisionRequest) -> ProposedDecision:
        """Return one proposed buy, sell, or hold action."""
