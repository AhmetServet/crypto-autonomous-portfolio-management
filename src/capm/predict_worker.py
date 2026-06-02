"""Isolated runtime prediction worker used by the live trading cycle."""

from __future__ import annotations

import argparse
import json

from capm.main import build_repository, parse_datetime
from capm.services.prediction_journal import PredictionJournalService
from capm.services.prediction_runtime import PredictionRuntimeService


def main() -> None:
    """Run and journal one artifact prediction in an isolated process."""
    parser = argparse.ArgumentParser(prog="python -m capm.predict_worker")
    parser.add_argument("--model-artifact", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", required=True)
    parser.add_argument("--at", required=True)
    args = parser.parse_args()

    repository = build_repository()
    prediction = PredictionRuntimeService(repository).predict(
        artifact_path=args.model_artifact,
        symbol=args.symbol,
        interval=args.interval,
        reference_time=parse_datetime(args.at),
    )
    journal_entry = PredictionJournalService(
        journal_repository=repository,
        market_data_repository=repository,
    ).journal_prediction(prediction)
    print(json.dumps({"status": "ok", "journal_id": journal_entry.id, "prediction": prediction.to_dict()}))


if __name__ == "__main__":
    main()
