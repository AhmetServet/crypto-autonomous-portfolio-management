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
- Deep-learning LLD: `docs/lld/deep_learning/lld.md`
- Prediction-journal LLD: `docs/lld/prediction_models/prediction_journal.md`
- Spot Demo trading-agent LLD: `docs/lld/trading_agent/spot_demo_trading_agent.md`
- Dashboard LLD: `docs/lld/dashboard/lld.md`

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
uv run capm-experiment-walkforward --config experiments/configs/recent_arima_btcusdt_1m_15m.json
```

Use `--env-file .env` if your database URL is not already in the environment. Set `"init_schema": true` in the JSON once if you need to create coinpair tables for the symbol before loading data. The CLI now prints progress logs to stderr while preserving the final JSON summary on stdout; pass `--quiet` to suppress those logs.

Metrics and run artifacts are written under `experiments/results/<run_id>/` (gitignored except `.gitkeep`) as a small consolidated set of files: `request.json`, `split_predictions.json`, `split_reports.json`, `trained_models.pkl`, and `summary.json`. `trained_models.pkl` stores the latest fitted model from each walk-forward split. Enable `"backtest": { "enabled": true, ... }` only after installing the `backtest` extra; it merges all walk-forward split predictions and runs one offline simulation over the same candle window.

### Production-style training and prediction
Production-style tabular training writes deployable `model.pkl` artifacts plus `summary.json` files. The full tabular preset compares XGBoost and LightGBM from one config:

```bash
uv run capm-train-production --config experiments/configs/full_tabular_compare_btcusdt_1m_15m.json
```

To compare XGBoost parameter profiles only, run:

```bash
uv run capm-train-production --config experiments/configs/xgboost_parameter_playground_btcusdt_1m_15m.json
```

To train the tuned LightGBM candidate only, run:

```bash
uv run capm-train-production --config experiments/configs/lightgbm_parameter_playground_btcusdt_1m_15m.json
```

To train the tuned LSTM sequence candidate, run:

```bash
uv run capm-train-deep-learning --config experiments/configs/lstm_parameter_playground_btcusdt_1m_15m.json
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
uv run capm-train-deep-learning --config experiments/configs/full_lstm_btcusdt_1m_15m.json
uv run capm-train-deep-learning --config experiments/configs/full_gru_btcusdt_1m_15m.json
```

The deep-learning CLI prints progress logs to stderr for long runs while preserving the final JSON summary on stdout. Use `--quiet` when only the JSON output is needed.

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

Dry-run writes to `agent_decision_journal`, applies hard risk checks, and never submits exchange orders. The Spot Demo path uses the same journal and risk gate before optional Demo order execution.

Run one LLM decision call across every symbol that currently has stored candles:

```bash
uv run capm agent run-once \
  --interval 1m \
  --mode dry-run \
  --policy llm \
  --show-prompt
```

Configure an OpenAI-compatible provider through:

```text
CAPM_LLM_BASE_URL=https://openrouter.ai/api/v1
CAPM_LLM_API_KEY=<provider API key>
CAPM_LLM_MODEL=<provider model identifier>
```

OpenRouter is the default base URL. Change the URL, key, and model to use another compatible chat-completions provider.

The LLM prompt includes current price, the latest five stored candles, persisted indicators, prediction direction and age, simulated portfolio balances, and hard risk limits. The response parser rejects invalid action sizing and confidence values before risk evaluation.

### Binance Spot Demo execution
Configure Spot Demo API credentials:

```text
CAPM_BINANCE_MODE=demo
CAPM_BINANCE_SPOT_REST_BASE_URL=https://demo-api.binance.com
CAPM_BINANCE_API_KEY=<Spot Demo API key>
CAPM_BINANCE_API_SECRET=<Spot Demo API secret>
```

Run one authenticated Spot Demo cycle:

```bash
uv run capm agent run-once \
  --interval 1m \
  --mode spot-demo \
  --policy llm \
  --max-trade-usdt 10 \
  --max-position-usdt 25 \
  --show-prompt
```

Spot Demo execution reads balances from Binance, applies the same hard risk gate, and submits only approved market orders. Before submission, the adapter caches Binance symbol filters, validates minimum notional values, and normalizes sell quantities to the allowed market step size. After submission, the agent persists the initial response and reconciles the latest order status. The adapter refuses the live Binance REST host.

Read Spot Demo balances without placing an order:

```bash
uv run capm spot-demo account --symbol BTCUSDT
```

Submit one explicit Spot Demo market-buy smoke test:

```bash
uv run capm spot-demo test-market-buy \
  --symbol BTCUSDT \
  --usdt-amount 10 \
  --confirm
```

The smoke-test command is separate from the LLM loop and refuses to run without `--confirm`.

Run one closed-candle live pipeline cycle in dry-run mode:

```bash
uv run capm agent run-live-once \
  --interval 1m \
  --mode dry-run \
  --model-artifact BTCUSDT=experiments/results/<xgboost_run_id>/model.pkl \
  --model-artifact BTCUSDT=experiments/results/<lstm_run_id>/model.pkl
```

`run-live-once` acquires a PostgreSQL advisory lock for the candle boundary, fills missing closed candles through REST, recalculates the recent persisted indicator window, settles matured predictions, journals one new prediction per configured model artifact, and runs one batched LLM decision call. Each artifact prediction runs in an isolated worker process so native ML runtimes such as XGBoost and PyTorch do not load conflicting OpenMP libraries into the same process. Repeat `--model-artifact SYMBOL=PATH` for each production model. The default is dry-run; pass `--mode spot-demo` explicitly to allow approved Demo orders.

Run the same pipeline continuously after each closed 1m candle:

```bash
uv run capm agent run-loop \
  --interval 1m \
  --mode dry-run \
  --max-cycles 3 \
  --model-artifact BTCUSDT=experiments/results/<xgboost_run_id>/model.pkl \
  --model-artifact BTCUSDT=experiments/results/<lstm_run_id>/model.pkl
```

`run-loop` sleeps until shortly after the next candle boundary, calls the same live-cycle service, prints one JSON payload per cycle, and closes clients when it exits. Use `--max-cycles` for smoke tests; omit it for unattended operation. `--stop-after-error-count` and `--sleep-after-error-seconds` bound repeated safe failures without bypassing operational risk controls.

The live cycle stops before prediction and trading when the candle gap exceeds `180` minutes or a model artifact file is older than `3` days. Retrain stale models before production use. For an explicit recovery check, use `--allow-large-gap-recovery` to backfill a longer candle gap and `--allow-stale-models` only when you intentionally want to validate the pipeline with an outdated artifact. Adjust the thresholds with `--max-inline-gap-minutes` and `--max-model-age-days`.

Spot Demo submissions also pass persistent operational controls derived from `agent_decision_journal`: emergency stop, FIFO daily realized-loss limit, maximum orders per day, order cooldown, and priced exposure limit. Defaults are `50` USDT realized loss, `20` orders per day, `5` cooldown minutes, and `100` USDT exposure. Override them with the corresponding `--max-*` flags. Set `CAPM_TRADING_EMERGENCY_STOP=true` to block submissions without changing scheduler arguments.

The first operational snapshot is symbol-scoped: exposure, daily order count, cooldown, and FIFO realized PnL are calculated for the current symbol. FIFO realized PnL uses persisted exchange quote quantities and does not convert fees charged in third-party assets into USDT. Extend these controls to account scope before enabling a multi-coin portfolio.

Show a recent operational report:

```bash
uv run capm agent report \
  --symbol BTCUSDT \
  --interval 1m \
  --limit 20
```

The report includes the latest candle and indicator row, current derived position state, recent prediction-journal rows, recent agent decisions, prediction and decision summaries over the last 24 hours, and the current symbol-scoped operational-risk snapshot. Add `--include-prompts` to include stored LLM prompt metadata, and `--include-spot-demo` to read current Spot Demo balances.

Run the dashboard API:

```bash
uv run capm-api --host 127.0.0.1 --port 8000
```

Swagger/OpenAPI is available at `http://127.0.0.1:8000/docs`.

The dashboard API exposes:

- `GET /api/health`
- `GET /api/symbols?interval=1m`
- `GET /api/dashboard/summary?symbol=BTCUSDT&interval=1m`
- `GET /api/charts/dashboard?symbol=BTCUSDT&interval=1m&lookback_hours=24`
- `GET /api/agent/decisions?symbol=BTCUSDT&interval=1m&limit=50`
- `GET /api/execution/orders?symbol=BTCUSDT&interval=1m&limit=50`
- `GET /api/predictions?symbol=BTCUSDT&interval=1m&limit=100`
- `GET /api/positions?symbol=BTCUSDT&interval=1m`
- `GET /api/risk/status?symbol=BTCUSDT`
- `GET /api/llm/prompts/<journal_id>`
- `GET /api/spot-demo/portfolio?symbol=BTCUSDT`
- `GET /api/model-artifacts?symbol=BTCUSDT&interval=1m`
- `GET /api/training/presets`
- `GET /api/training/jobs`
- `GET /api/training/jobs/<job_id>`
- `GET /api/data/coverage?symbol=BTCUSDT&interval=1m`
- `GET /api/agent/loops`
- `GET /api/agent/loops/<loop_id>`
- `POST /api/agent/run-once`
- `POST /api/agent/run-live-once`
- `POST /api/agent/loops`
- `POST /api/agent/loops/<loop_id>/stop`
- `POST /api/predict`
- `POST /api/predict/batch`
- `POST /api/predictions/settle`
- `POST /api/prediction-journal/summary`
- `POST /api/database/init`
- `POST /api/market/fetch-ohlcv`
- `POST /api/market/ingest-ohlcv`
- `POST /api/market/repair-ohlcv-gaps`
- `POST /api/features/backfill-indicators`
- `POST /api/training/jobs`
- `POST /api/training/jobs/<job_id>/cancel`
- `POST /api/model-artifacts/state`
- `POST /api/spot-demo/market-buy`
- `POST /api/spot-demo/market-sell`

Manual Spot Demo order endpoints require `confirm: true` in the JSON body. Example:

```bash
curl -X POST http://127.0.0.1:8000/api/spot-demo/market-buy \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","usdt_amount":10,"confirm":true}'
```

Run the dashboard frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API at `http://127.0.0.1:8000` by default. Override it with `VITE_CAPM_API_BASE_URL` when needed.

Current dashboard capabilities:
- Overview: health, freshness, position/risk, Chart.js price chart with candlestick-style OHLC overlay, buy/sell/hold markers, indicator chart, realized PnL curve, live status beacon, risk meters, active model cards, and decision timeline.
- Trade: Spot Demo portfolio, confirmed manual market buy/sell, recent execution orders, raw order drawer, and realized PnL columns.
- Agent: shared runtime configuration, risk presets/limits, run-once, continuous live loop start/stop, loop logs, and manual agent action controls.
- Data: database init, OHLCV fetch/ingest, data coverage, gap repair, and indicator backfill.
- Models: training presets, generated config preview, training job queue/logs/cancel, active model cards, prediction runtime tools, prediction settlement, prediction summary, and model registry state controls.
- Journal: recent decisions, recent predictions, execution orders, prompt drawer, and raw LLM responses.

Frontend quality checks:

```bash
cd frontend
npm run lint
npm run build
```

Summarize recorded decisions:

```bash
uv run capm agent journal summary \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2026-05-01T00:00:00Z \
  --end 2026-05-30T00:00:00Z
```
