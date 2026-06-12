# Dashboard LLD

## 1. Purpose
This document describes the current dashboard and API design for operating CAPM without using the CLI for day-to-day workflows.

The dashboard is intended to expose the same operational capabilities already available through CLI commands:
- inspect system health, market freshness, positions, predictions, decisions, risk state, and execution orders
- manage OHLCV and indicator data
- train models from curated presets
- inspect and manage model artifacts
- run predictions and settle prediction journals
- run the trading agent once or as a continuous loop
- submit manual Binance Spot Demo orders

This document complements:
- `docs/lld/trading_agent/spot_demo_trading_agent.md`
- `docs/lld/prediction_models/lld.md`
- `docs/lld/prediction_models/prediction_journal.md`
- `docs/lld/deep_learning/lld.md`
- `docs/lld/data_store/lld.md`

## 2. Current Stack

Backend:
- FastAPI application under `src/capm/api`
- Console entrypoint: `uv run capm-api --host 127.0.0.1 --port 8000`
- Automatic Swagger/OpenAPI docs at `/docs`
- Routers split by responsibility:
  - `dashboard.py`
  - `market.py`
  - `predictions.py`
  - `trading.py`
  - `training.py`

Frontend:
- React + Vite under `frontend/`
- API base URL: `VITE_CAPM_API_BASE_URL`, default `http://127.0.0.1:8000`
- Chart rendering: Chart.js through `react-chartjs-2`
- Icon set: `lucide-react`
- Primary UI files:
  - `frontend/src/App.tsx`
  - `frontend/src/App.css`
  - `frontend/src/dashboard/*`

## 3. Design Principles

Rules:
- UI actions must call native API endpoints, not shell commands.
- API routers must stay thin and call services.
- Manual Spot Demo orders must require explicit confirmation.
- Live trading defaults to dry-run unless Spot Demo mode is explicitly selected.
- Model artifact selection should use the registry rather than hand-typed paths.
- Shared runtime settings must live in a shared panel when they affect multiple actions.
- Charts must remain responsive and avoid heavy SVG marker rendering for long time windows.

Current visual style:
- dark Binance-inspired dashboard
- sharp corners
- black/blue-gray surfaces with yellow accent
- green/red semantic states for positive/negative trading outcomes
- dense operational layout, not a marketing page

## 4. API Surface

Dashboard and observability:

```text
GET /api/health
GET /api/symbols?interval=1m
GET /api/dashboard/summary?symbol=BTCUSDT&interval=1m&limit=20&lookback_hours=24
GET /api/charts/dashboard?symbol=BTCUSDT&interval=1m&lookback_hours=24&limit=720
GET /api/agent/decisions?symbol=BTCUSDT&interval=1m&limit=50
GET /api/execution/orders?symbol=BTCUSDT&interval=1m&limit=50
GET /api/predictions?symbol=BTCUSDT&interval=1m&limit=100
GET /api/positions?symbol=BTCUSDT&interval=1m
GET /api/risk/status?symbol=BTCUSDT
GET /api/llm/prompts/{journal_id}
```

Market data and features:

```text
POST /api/database/init
POST /api/market/fetch-ohlcv
POST /api/market/ingest-ohlcv
GET  /api/data/coverage
POST /api/market/repair-ohlcv-gaps
POST /api/features/backfill-indicators
```

Prediction runtime:

```text
POST /api/predict
POST /api/predict/batch
POST /api/predictions/settle
POST /api/prediction-journal/summary
```

Trading and agent control:

```text
POST /api/agent/run-once
POST /api/agent/run-live-once
GET  /api/agent/loops
GET  /api/agent/loops/{loop_id}
POST /api/agent/loops
POST /api/agent/loops/{loop_id}/stop
POST /api/agent/journal/summary
GET  /api/spot-demo/portfolio?symbol=BTCUSDT
POST /api/spot-demo/market-buy
POST /api/spot-demo/market-sell
```

Training and registry:

```text
GET  /api/model-artifacts
POST /api/model-artifacts/state
GET  /api/training/presets
GET  /api/training/jobs
GET  /api/training/jobs/{job_id}
POST /api/training/jobs
POST /api/training/jobs/{job_id}/cancel
```

## 5. Frontend Sections

Top-level tabs:
- Overview
- Trade
- Agent
- Data
- Models
- Journal

### 5.1 Overview
Purpose: fastest read of current system state.

Components:
- metric cards for latest price, latest agent decision, prediction accuracy, model count, API health
- Chart.js dashboard charts:
  - price chart with candlestick-style OHLC overlay
  - buy/sell/hold markers
  - indicator detail chart
  - realized PnL curve
- visual summary rail:
  - position/PnL hero
  - live status beacon
  - risk meters
  - active model cards
  - decision timeline
- market state, indicator state, and health panels

### 5.2 Trade
Purpose: inspect and manually exercise Binance Spot Demo execution.

Components:
- Spot Demo portfolio snapshot
- manual market buy form
- manual market sell form
- execution/orders table
- raw order drawer

Manual order safety:
- buy and sell forms require a confirmation checkbox
- manual endpoints require `confirm: true`
- UI does not hide raw exchange response details

### 5.3 Agent
Purpose: run and supervise trading-agent cycles.

Components:
- Runtime Configuration shared by run-once and continuous loop:
  - trading mode
  - market-data mode
  - large-gap recovery override
  - stale-model override
- Risk Controls:
  - emergency stop
  - max trade size
  - max position size
  - daily realized-loss cap
  - max orders per day
  - cooldown
  - max exposure
  - presets
- Run Agent Once
- Live Agent Loop start/stop
- loop status, PID, return code, log viewer
- manual threshold/LLM action controls

Layout note:
- Agent uses packed columns to avoid visual gaps between panels with different heights.

### 5.4 Data
Purpose: manage local market and feature data.

Components:
- init database for selected symbols
- fetch OHLCV preview or persist flow
- ingest OHLCV through REST, dump, or dump-with-rest-tail
- coverage inspection
- missing candle repair
- indicator backfill

Current rule:
- large historical ingestion still belongs in background/CLI when the user wants full control over terminal output, but the UI exposes equivalent native actions.

### 5.5 Models
Purpose: train, inspect, activate, and use models.

Components:
- active model cards
- training panel with preset selector and generated config preview
- training jobs table with logs and cancellation
- prediction tools:
  - single model prediction
  - all active model prediction
  - journal toggle
  - settle predictions
  - prediction summary
- model registry:
  - filters by type/status
  - metrics columns
  - active/inactive toggle
  - archive/unarchive toggle

### 5.6 Journal
Purpose: inspect audit trail.

Components:
- recent decisions
- recent predictions
- execution orders
- prompt drawer for LLM prompts and raw responses

## 6. Chart Design

The dashboard uses Chart.js instead of Recharts because 24h 1m windows with many markers caused hover lag and noisy tooltips in Recharts.

Chart.js choices:
- canvas rendering for better pointer performance
- animations disabled for operational charts
- normalized data enabled
- point radius disabled for line series
- decision markers as separate datasets
- hold markers hidden from legend/tooltip noise
- candlestick-style OHLC overlay implemented as a lightweight Chart.js plugin from existing candle rows

Data source:
- `GET /api/charts/dashboard`
- returns candles, prediction markers, decision markers, and PnL curve rows

## 7. Training Jobs

Training jobs are started by API and run as subprocesses.

Current behavior:
- dashboard writes generated config files under `experiments/results/dashboard_jobs/<job_id>/config.json`
- job logs are streamed from local job metadata
- cancel sends a stop request for the running process
- model registry refreshes after training completion

Supported model families:
- tabular: XGBoost, LightGBM
- deep learning: LSTM, GRU
- statistical: ARIMA, Prophet

## 8. Model Registry

The registry scans artifacts under `experiments/results`.

Artifacts are selectable only when:
- `active = true`
- `archived = false`
- symbol and interval match the current selection

Displayed metadata:
- model name
- model type
- trained-through timestamp
- accuracy
- RMSE
- MAPE
- cumulative return
- trade count
- stale status

## 9. Operational Safety

UI does not bypass backend risk controls.

Risk-sensitive actions:
- Spot Demo manual buy/sell requires explicit confirmation
- agent live loop uses the same backend risk config as CLI
- emergency stop is passed through the risk configuration
- large-gap recovery and stale-model overrides are visible shared runtime settings
- Spot Demo mode must be explicitly selected

## 10. How To Run

API:

```bash
uv run capm-api --host 127.0.0.1 --port 8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Optional API override:

```bash
VITE_CAPM_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Quality checks:

```bash
cd frontend
npm run lint
npm run build
```

## 11. Known Limitations

- Authentication is not implemented yet.
- Dashboard live loops are tracked inside the API process and are not yet durable across API restarts.
- Training job state is local to the API process and results directory.
- Portfolio/risk calculations are currently symbol-scoped for the initial BTCUSDT flow.
- Chart candlestick overlay is a visual overlay, not a dedicated financial charting package.
- Multi-coin portfolio UI is intentionally postponed until the project trains and validates more symbols.

## 12. Future Work

- Add authentication and local-only network guardrails.
- Persist dashboard job and loop state in the database.
- Add account-wide portfolio and risk views.
- Add multi-symbol selector groups when more symbols are trained.
- Add export for chart data and journal tables.
- Add WebSocket/SSE streaming for live loop logs instead of polling.
