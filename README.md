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
uv run capm-init-db --symbol BTCUSDT
```

Bootstrap now creates the shared `coinpairs`, `ohlcv_coverage`, `feature_coverage`, and `indicator_coverage` tables. Logical symbols are still passed as `BTCUSDT`, but the physical raw/derived tables are created with id-based names such as `coinpair_1_ohlcv` and `coinpair_1_feature`.

### Fetch OHLC Data
The CLI currently supports historical OHLCV retrieval from Binance spot demo mode or live mode.

```bash
uv run capm fetch-ohlc \
  --symbol BTC/USDT \
  --interval 1m \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-01T01:00:00Z \
  --mode demo
```

Notes:
- `--start` is inclusive.
- `--end` is exclusive.
- Supported intervals currently include `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, and `1w`.
- In repository-backed ingestion flows, stored coverage is checked first so fully covered ranges are served from DB and only missing gaps are fetched from Binance.

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
- optional Backtrader integration under `src/capm/services/backtesting`

These components are designed to read stored candles and feature rows through the existing repository ports rather than querying Binance directly for experiment datasets.

### Walk-forward experiments
Example configs live under `experiments/configs/`. After you have ingested OHLCV into the database (and, for `xgboost` / `lightgbm`, persisted the matching feature columns), run:

```bash
uv run capm-experiment-walkforward --config experiments/configs/walk_forward_arima.example.json
```

Use `--env-file .env` if your database URL is not already in the environment. Set `"init_schema": true` in the JSON once if you need to create coinpair tables for the symbol before loading data. The CLI now prints progress logs to stderr while preserving the final JSON summary on stdout; pass `--quiet` to suppress those logs.

Metrics and run artifacts are written under `experiments/results/<run_id>/` (gitignored except `.gitkeep`) as a small consolidated set of files: `request.json`, `split_predictions.json`, `split_reports.json`, `trained_models.pkl`, and `summary.json`. `trained_models.pkl` stores the latest fitted model from each walk-forward split. Enable `"backtest": { "enabled": true, ... }` only after installing the `backtest` extra; it merges all walk-forward split predictions and runs one offline simulation over the same candle window.