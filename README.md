# Autonomous Portfolio Management in Crypto Spot Markets: Experimental Analysis and Development of Hybrid Artificial Intelligence Approaches

This is the monorepo of our graduation project. Everything including docs, analyses and source code stays here.

## Our Team
- Ahmet Servet Polat
- Kenan Koçoğlu
- Mehmet Enes Odabaş

## Python Workspace
The first implementation slice now includes a Python package under `src/capm` for Binance spot market-data ingestion.

### Documentation
- Binance market-data LLD: `docs/lld/binance_spot_market_data/lld.md`
- Data-store LLD: `docs/lld/data_store/lld.md`
- Prediction-model LLD: `docs/lld/prediction_models/lld.md`

### Setup
```bash
uv sync
```

Install optional extras for forecasting and backtesting work:
```bash
uv sync --extra ml --extra backtest --extra notebooks
```

Create a local environment file before running the storage example:
```bash
cp .env.example .env
```

For large backfills on smaller Postgres instances, these optional settings can reduce write pressure and keep SQLAlchemy errors compact:
```bash
CAPM_DATABASE_OHLCV_WRITE_BATCH_SIZE=500
CAPM_DATABASE_HIDE_SQL_PARAMETERS=true
```

Initialize the CAPM schema before the first ingestion run:
```bash
uv run capm init-db --symbol BTCUSDT
```

Bootstrap now creates the shared `coinpairs`, `ohlcv_coverage`, `feature_coverage`, and `indicator_coverage` tables. Logical symbols are still passed as `BTCUSDT`, but the physical raw/derived tables are created with id-based names such as `coinpair_1_ohlcv` and `coinpair_1_feature`.

### Fetch and Ingest OHLCV Data
The CLI has one main entrypoint under `uv run capm`.

Print a small historical OHLCV range from Binance spot without writing to the database:

```bash
uv run capm fetch-ohlc \
  --symbol BTC/USDT \
  --interval 1m \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-01T01:00:00Z \
  --mode demo
```

Persist a range through REST while using stored coverage to skip already-loaded candles:

```bash
uv run capm ingest-ohlcv \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-02T00:00:00Z \
  --source rest
```

For large historical backfills, prefer Binance public data dumps. This downloads monthly ZIP files from `data.binance.vision`, filters the requested half-open time range, writes candles to the DB, and then fills missing or unreleased months with REST:

```bash
uv run capm ingest-ohlcv \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2021-05-26T00:00:00Z \
  --end 2026-05-26T00:00:00Z \
  --source dump-with-rest-tail \
  --batch-size 50000
```

Use `--source dump` if you only want released public dump files and do not want REST gap filling.

Notes:
- `--start` is inclusive.
- `--end` is exclusive.
- Supported intervals currently include `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, and `1w`.
- Repository-backed ingestion checks `ohlcv_coverage` first. Covered REST ranges are skipped, and covered dump months are not downloaded again.
- Binance public dump URLs follow `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip`.

### Tests
```bash
uv run python -m unittest discover -s tests -t . -v
```

### Prediction Slice
The first forecasting implementation slice now includes:
- prediction-domain contracts and metrics under `src/capm/domains/prediction`
- shared forecasting protocols under `src/capm/core/contracts/prediction.py`
- model wrappers and registry under `src/capm/models`
- DB-backed dataset loading plus walk-forward runners under `src/capm/services/training`
- runtime prediction loading under `src/capm/services/prediction_runtime.py`
- optional Backtrader integration under `src/capm/services/backtesting`

These components are designed to read stored candles and feature rows through the existing repository ports rather than querying Binance directly for experiment datasets.

### Walk-forward experiments
Example configs live under `experiments/configs/`. After you have ingested OHLCV into the database (and, for `xgboost` / `lightgbm`, persisted the matching feature columns), run:

```bash
uv run capm-experiment-walkforward --config experiments/configs/walk_forward_arima.example.json
```

Use `--env-file .env` if your database URL is not already in the environment. Set `"init_schema": true` in the JSON once if you need to create coinpair tables for the symbol before loading data. The CLI now prints progress logs to stderr while preserving the final JSON summary on stdout; pass `--quiet` to suppress those logs.

Metrics and run artifacts are written under `experiments/results/<run_id>/` (gitignored except `.gitkeep`) as a small consolidated set of files: `request.json`, `split_predictions.json`, `split_reports.json`, `trained_models.pkl`, and `summary.json`. `trained_models.pkl` stores the latest fitted model from each walk-forward split. Enable `"backtest": { "enabled": true, ... }` only after installing the `backtest` extra; it merges all walk-forward split predictions and runs one offline simulation over the same candle window.

### Production-style training and prediction
Production-style tabular training writes a deployable `model.pkl` artifact plus a `summary.json`:

```bash
uv run capm-train-production --config experiments/configs/train_xgboost_production.example.json
```

Compare XGBoost and LightGBM from one config:

```bash
uv run capm-train-production --config experiments/configs/compare_tabular_production.example.json
```

Run one prediction from a saved production model or a walk-forward `trained_models.pkl` artifact:

```bash
uv run capm predict \
  --model-artifact experiments/results/<run_id>/model.pkl \
  --symbol BTCUSDT \
  --interval 1m
```

Use `--at 2026-05-25T21:48:00Z` to predict from a specific candle open time instead of the latest stored row. Tabular production artifacts validate that the persisted feature row contains the exact feature names saved with the model.

Deep-learning sequence models are optional because they require PyTorch. Install the extra before training LSTM or GRU artifacts:

```bash
uv sync --extra deep-learning
```

Train one LSTM or GRU production artifact:

```bash
uv run capm-train-deep-learning --config experiments/configs/train_lstm_production.example.json
uv run capm-train-deep-learning --config experiments/configs/train_gru_production.example.json
```

The deep-learning CLI prints progress logs to stderr for long runs while preserving the final JSON summary on stdout. Use `--quiet` when only the JSON output is needed.

Compare both recurrent models from one config:

```bash
uv run capm-train-deep-learning --config experiments/configs/compare_deep_learning.example.json
```

The deep-learning trainer reads ready feature rows from the database, builds causal sequence windows, fits the feature scaler on the train split only, writes `model.pkl` and `summary.json`, and runs the same holdout Backtrader evaluation path as production tabular models. Saved artifacts use `artifact_kind = "deep_learning_sequence"` and can be passed to `uv run capm predict` with the same command shown above.

### Prediction journal
Persist runtime predictions when you want to evaluate live or daytime model behavior after the forecast horizon passes:

```bash
uv run capm predict \
  --model-artifact experiments/results/<run_id>/model.pkl \
  --symbol BTCUSDT \
  --interval 1m \
  --journal
```

Settle journal rows once the target candles exist:

```bash
uv run capm settle-predictions \
  --symbol BTCUSDT \
  --interval 1m
```

Summarize settled journal quality:

```bash
uv run capm prediction-journal summary \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2026-05-01T00:00:00Z \
  --end 2026-05-30T00:00:00Z
```

### Trading-agent dry run
Run one deterministic, auditable dry-run decision against the latest stored candle and recent prediction-journal rows:

```bash
uv run capm agent run-once \
  --symbol BTCUSDT \
  --interval 1m \
  --mode dry-run
```

This first slice writes to `agent_decision_journal`, applies hard risk checks, and never submits exchange orders. Spot Demo execution and the LLM decision policy are added after this dry-run foundation.

Summarize recorded decisions:

```bash
uv run capm agent journal summary \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2026-05-01T00:00:00Z \
  --end 2026-05-30T00:00:00Z
```
