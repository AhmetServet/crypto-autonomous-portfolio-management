"""Machine-readable hard risk validation results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RiskViolation:
    """One rejected risk rule."""

    rule: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "message": self.message, "details": self.details}


@dataclass(frozen=True, slots=True)
class RiskResult:
    """Result of evaluating one proposed decision."""

    status: str
    violations: tuple[RiskViolation, ...] = ()
