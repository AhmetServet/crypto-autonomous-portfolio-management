"""Local artifact persistence for experiment runs."""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LocalArtifactStore:
    """Persists experiment artifacts under a configurable workspace path."""

    base_path: Path | str = Path("experiments/results")

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_path", Path(self.base_path))

    def write_json(self, *, run_id: str, relative_path: str, payload: Any) -> str:
        """Persist one JSON artifact beneath the run directory."""
        target_path = self.base_path / run_id / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return str(target_path)

    def write_pickle(self, *, run_id: str, relative_path: str, payload: Any) -> str:
        """Persist one pickle artifact beneath the run directory."""
        target_path = self.base_path / run_id / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as artifact_file:
            pickle.dump(payload, artifact_file)
        return str(target_path)
