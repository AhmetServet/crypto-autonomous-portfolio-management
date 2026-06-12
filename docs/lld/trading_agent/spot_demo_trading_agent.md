# Spot Demo Trading Agent LLD

## 1. Purpose
This document describes the low-level design for the first Binance Spot Demo Mode trading-agent slice in `src/capm`.

The goal is to prove that the system can run one controlled trading cycle end to end:

```text
latest market state
  -> latest model predictions
  -> agent decision
  -> risk validation
  -> decision journal
  -> optional Binance Spot Demo Mode order
```

This slice is not intended to make the strategy profitable. It is intended to make the trading loop executable, auditable, and safe enough to run against Binance Spot Demo Mode.

Terminology:
- this branch targets Binance Spot Demo Mode, not Binance Spot Testnet
- Spot Demo Mode is preferred here because it is intended for testing against realistic market data and live-exchange-like behavior
- Spot Testnet is a separate environment that is useful for integrating upcoming spot features before they are available on the live exchange

This document complements:
- `docs/requirements/requirements_analysis.md`
- `docs/implementation_design/design.md`
- `docs/lld/prediction_models/prediction_journal.md`
- `docs/lld/data_store/lld.md`
- `docs/lld/indicators/lld.md`

## 2. Problem
The project can ingest market data, calculate indicators, train models, run predictions, and persist prediction outcomes. The missing layer is the controlled decision and execution loop.

Current gaps:
- no persistent record of buy, sell, or hold decisions
- no standard decision payload for an AI agent or deterministic policy
- no risk-control gate between decisions and exchange orders
- no Binance Spot Demo Mode execution adapter
- no way to dry-run the same decision path without placing orders
- no single CLI command that exercises the trading loop
- no audit trail linking model predictions to later agent actions

The Spot Demo trading agent fills this gap. It consumes stored predictions and market state, writes a decision journal, applies hard risk checks, and can optionally send approved orders to Binance Spot Demo Mode.

## 3. Scope
Included in scope:
- define trading-agent domain entities for decisions, actions, risk checks, and execution results
- add an `agent_decision_journal` table for all buy, sell, and hold decisions
- support one-symbol `run-once` execution from the CLI
- support `dry-run` mode that never contacts Binance order endpoints
- support `spot_demo` mode that uses Binance Spot Demo Mode credentials and base URL
- read latest settled or unsettled prediction signals from `prediction_journal`
- read latest candle and recent candle context from the local database
- read balances and open orders from Binance Spot Demo Mode in `spot_demo` mode
- apply hard risk controls before any order is submitted
- write risk rejections and execution attempts to the decision journal
- produce structured CLI output suitable for scheduled jobs later

Out of scope:
- live Binance mainnet execution
- production-grade external scheduler
- nightly retraining orchestration
- portfolio optimization across all top-20 symbols
- full LLM prompt optimization
- advanced order types beyond simple spot market or limit order intents
- exchange websocket account streams
- profit-and-loss attribution for completed strategies

## 4. Design Drivers
The design is shaped by:
- Spot Demo-first safety
- auditable trading decisions
- existing prediction journal persistence
- hard risk controls that cannot be overridden by an AI response
- a future per-minute worker loop
- local reproducibility through dry-run mode
- current modular-monolith architecture with domains, contracts, infra adapters, and services

Pragmatic decisions:
- implement `run-once` before scheduling
- start with one symbol and one interval, then generalize to scan-universe batches
- journal all decisions, including `hold`
- keep decisioning deterministic by default, with an AI-agent adapter added behind a contract
- use one `agent_decision_journal` table for all symbols, modes, and experiments
- keep order execution and decision journaling separate from prediction journaling

## 5. Target Module Layout
Target layout:

```text
src/capm/
├─ core/
│  └─ contracts/
│     ├─ trading.py
│     └─ prediction.py
├─ domains/
│  ├─ trading/
│  │  ├─ __init__.py
│  │  ├─ decision.py
│  │  ├─ execution.py
│  │  └─ risk.py
│  └─ prediction/
│     └─ journal.py
├─ infra/
│  ├─ database/
│  │  ├─ models.py
│  │  └─ timescale.py
│  └─ exchange/
│     ├─ __init__.py
│     └─ binance_spot_demo.py
└─ services/
   ├─ trading_agent.py
   ├─ risk_control.py
   └─ decision_policy.py
```

Responsibilities:
- `domains/trading/decision.py`
  - decision request, action, normalized action values, journal entry, and validation
- `domains/trading/risk.py`
  - risk rule identifiers, risk validation results, and violation details
- `domains/trading/execution.py`
  - order intent and exchange execution result entities
- `core/contracts/trading.py`
  - repository, exchange, portfolio, decision-policy, and risk-control ports
- `infra/database/timescale.py`
  - `agent_decision_journal` persistence implementation
- `infra/exchange/binance_spot_demo.py`
  - Binance Spot Demo Mode REST adapter for balances, open orders, submit order, and cancel order
- `services/decision_policy.py`
  - deterministic baseline policy and future AI-agent policy interface
- `services/risk_control.py`
  - hard rule validation before execution
- `services/trading_agent.py`
  - orchestration for one trading cycle
- `src/capm/main.py`
  - CLI command wiring

## 6. Data Model
Recommended table name:

```text
agent_decision_journal
```

Recommended columns:

```sql
id BIGSERIAL PRIMARY KEY,
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

cycle_id TEXT NOT NULL,
mode TEXT NOT NULL,
symbol TEXT NOT NULL,
interval TEXT NOT NULL,
reference_time TIMESTAMPTZ NOT NULL,

action TEXT NOT NULL,
requested_quantity DOUBLE PRECISION,
requested_usdt_amount DOUBLE PRECISION,
confidence DOUBLE PRECISION,
reason TEXT,

prediction_journal_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
prediction_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
market_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
portfolio_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,

risk_status TEXT NOT NULL,
risk_violations JSONB NOT NULL DEFAULT '[]'::jsonb,

execution_status TEXT NOT NULL,
exchange_order_id TEXT,
exchange_client_order_id TEXT,
exchange_response JSONB NOT NULL DEFAULT '{}'::jsonb,

metadata JSONB NOT NULL DEFAULT '{}'::jsonb
```

Action values:
- `buy`
- `sell`
- `hold`

Mode values:
- `dry_run`
- `spot_demo`

CLI values should use hyphenated names such as `spot-demo`. Domain entities and persisted rows should normalize that value to `spot_demo`.

Risk status values:
- `approved`
- `rejected`
- `skipped`

Execution status values:
- `not_submitted`
- `submitted`
- `filled`
- `partially_filled`
- `cancelled`
- `rejected`
- `failed`

Reason:
- one table can store all coins, models, modes, and experiments
- rows are separated by `symbol`, `interval`, `mode`, `cycle_id`, and `reference_time`
- decision records should remain queryable across symbols for portfolio-level analysis

## 7. Constraints And Indexes
Recommended indexes:

```sql
CREATE INDEX agent_decision_journal_symbol_time_idx
  ON agent_decision_journal (symbol, interval, reference_time DESC);

CREATE INDEX agent_decision_journal_cycle_idx
  ON agent_decision_journal (cycle_id);

CREATE INDEX agent_decision_journal_mode_time_idx
  ON agent_decision_journal (mode, created_at DESC);

CREATE INDEX agent_decision_journal_execution_idx
  ON agent_decision_journal (execution_status, created_at DESC);
```

Recommended idempotency rule:

```sql
UNIQUE (
  cycle_id,
  symbol,
  interval
)
```

Reason:
- retries of the same trading cycle should not duplicate decisions
- each symbol in a cycle should have one final journal row
- later scan-universe support can use the same `cycle_id` across many symbols

## 8. Decision Input
The trading agent builds a normalized decision request from local and external state.

Minimum request shape:

```json
{
  "cycle_id": "2026-05-30T00:01:00Z:BTCUSDT:1m",
  "mode": "dry_run",
  "symbol": "BTCUSDT",
  "interval": "1m",
  "reference_time": "2026-05-30T00:00:00Z",
  "latest_candle": {
    "open": 68000.0,
    "high": 68100.0,
    "low": 67950.0,
    "close": 68050.0,
    "volume": 123.45
  },
  "recent_candles": [],
  "predictions": [],
  "portfolio": {
    "available_usdt": 10000.0,
    "base_asset_free": 0.0,
    "base_asset_locked": 0.0
  },
  "risk_config": {
    "max_trade_usdt": 100.0,
    "min_confidence": 0.55,
    "max_position_usdt": 1000.0
  }
}
```

Prediction inputs should come from `prediction_journal` rows for the same symbol and interval, preferably anchored at the same `reference_time`.

Initial selection rule:
- choose the latest prediction rows where `symbol`, `interval`, and `reference_time` match the latest complete candle
- if no exact reference-time prediction exists, choose the latest prediction rows before the latest complete candle within a configurable staleness window
- if no usable prediction exists, the default decision is `hold`

## 9. Decision Policy
The first implementation should include a deterministic policy before introducing an LLM adapter.

Reason:
- deterministic behavior is easier to test
- it proves the data, risk, journal, and execution path first
- LLM prompt design can be added after the plumbing is reliable

Baseline policy:
- if there is no prediction, return `hold`
- if predicted direction is `up` and confidence or absolute predicted return passes threshold, request `buy`
- if predicted direction is `down` and current holdings are positive, request `sell`
- otherwise return `hold`

The policy must return a normalized action:

```json
{
  "action": "buy",
  "requested_usdt_amount": 25.0,
  "requested_quantity": null,
  "confidence": 0.61,
  "reason": "latest model signal is up and above threshold"
}
```

Future AI-agent policy:
- build one compact prompt per scan cycle
- parse strict JSON
- retry malformed responses up to three total attempts
- pass parsed actions through the same risk-control service
- never allow the AI adapter to submit orders directly

## 10. Risk Control
Risk control is a hard gate between decision policy output and execution.

Initial hard rules:

| Rule | Condition | Result |
| --- | --- | --- |
| invalid action | action is not `buy`, `sell`, or `hold` | reject |
| hold action | action is `hold` | skip execution |
| missing market data | latest candle is missing | reject |
| stale prediction | prediction is older than configured staleness window | reject or force hold |
| low confidence | confidence below configured minimum | reject or force hold |
| max trade size | requested USDT amount exceeds config | reject |
| insufficient USDT | buy amount exceeds available USDT | reject |
| zero balance sell | sell requested with no base asset balance | reject |
| max position size | buy would exceed configured position cap | reject |
| Spot Demo credentials missing | mode is `spot_demo` and credentials are absent | reject |

Risk results should be machine-readable:

```json
{
  "status": "rejected",
  "violations": [
    {
      "rule": "insufficient_usdt",
      "message": "requested buy amount exceeds available USDT",
      "details": {
        "requested_usdt_amount": 100.0,
        "available_usdt": 50.0
      }
    }
  ]
}
```

## 11. Execution Adapter
The exchange adapter should be behind a port.

Required operations:
- get account balances
- get open orders for a symbol
- submit spot order
- cancel order
- get order status

Initial Spot Demo environment variables:

```text
CAPM_BINANCE_MODE=demo
CAPM_BINANCE_SPOT_REST_BASE_URL=https://demo-api.binance.com
CAPM_BINANCE_API_KEY=<Spot Demo API key>
CAPM_BINANCE_API_SECRET=<Spot Demo API secret>
```

Rules:
- never use mainnet credentials in this branch
- fail loudly if `--mode spot-demo` is used without Spot Demo credentials
- dry-run mode must not call order submission endpoints
- order requests and exchange responses must be journaled
- secrets must never be logged

Initial order support:
- market buy by quote amount where Binance supports quote order quantity
- market sell by base quantity

If Binance Spot Demo Mode rejects quote-quantity market buys for a symbol, fallback order behavior must be explicit and tested before use.

## 12. Run-Once Flow
Initial CLI:

```bash
uv run capm agent run-once \
  --symbol BTCUSDT \
  --interval 1m \
  --mode dry-run
```

Spot Demo mode:

```bash
uv run capm agent run-once \
  --symbol BTCUSDT \
  --interval 1m \
  --mode spot-demo
```

Flow:

1. Resolve latest complete candle for the symbol and interval.
2. Load matching or recent prediction journal rows.
3. Load portfolio state.
   - dry-run: use configured or default simulated balance
   - spot_demo: read balances from Binance Spot Demo Mode
4. Build a decision request.
5. Run the decision policy.
6. Run risk checks.
7. Write an `agent_decision_journal` row.
8. If mode is `dry_run`, stop before exchange execution.
9. If mode is `spot_demo` and risk is approved, submit the order.
10. Update the journal row with execution result.
11. Print structured JSON summary.

## 13. CLI Commands
Initial commands:

```bash
uv run capm agent decide \
  --symbol BTCUSDT \
  --interval 1m
```

```bash
uv run capm agent run-once \
  --symbol BTCUSDT \
  --interval 1m \
  --mode dry-run
```

```bash
uv run capm agent run-once \
  --symbol BTCUSDT \
  --interval 1m \
  --mode spot-demo
```

```bash
uv run capm agent journal summary \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2026-05-30T00:00:00Z \
  --end 2026-05-31T00:00:00Z
```

Command behavior:
- `agent decide` builds the input and returns the proposed decision without execution
- `agent run-once` runs decision, risk, journal, and optional execution
- `agent journal summary` reports counts by action, risk status, execution status, and mode

## 14. Configuration
Initial config can be CLI flags with conservative defaults.

Recommended flags:

```text
--mode dry-run|spot-demo
--symbol BTCUSDT
--interval 1m
--max-trade-usdt 25
--max-position-usdt 100
--min-confidence 0.55
--prediction-staleness-minutes 5
--dry-run-usdt-balance 1000
```

Future config file:

```json
{
  "mode": "dry_run",
  "symbols": ["BTCUSDT"],
  "interval": "1m",
  "risk": {
    "max_trade_usdt": 25.0,
    "max_position_usdt": 100.0,
    "min_confidence": 0.55,
    "prediction_staleness_minutes": 5
  },
  "policy": {
    "name": "threshold",
    "min_predicted_return": 0.0005
  }
}
```

## 15. Error Handling
Expected failures:
- missing latest candle
- no prediction rows
- stale prediction rows
- malformed decision policy output
- missing Spot Demo credentials
- Spot Demo request failure
- insufficient balance
- duplicate cycle submission

Handling rules:
- missing predictions should produce `hold` in dry-run and Spot Demo mode
- hard validation failures should be journaled as rejected decisions
- exchange failures should update `execution_status` to `failed`
- retries are allowed for transient network failures only
- duplicate cycle writes should return the existing journal row when safe

## 16. Observability
Every `run-once` command should print structured JSON:

```json
{
  "cycle_id": "2026-05-30T00:01:00Z:BTCUSDT:1m",
  "mode": "dry_run",
  "symbol": "BTCUSDT",
  "interval": "1m",
  "action": "hold",
  "risk_status": "skipped",
  "execution_status": "not_submitted",
  "journal_id": 123
}
```

Useful metrics for later:
- decision latency
- prediction age
- risk rejection count by rule
- order submission latency
- exchange failure count
- action counts by symbol and model

## 17. Test Strategy
Unit tests:
- action normalization and validation
- risk-control rule evaluation
- deterministic decision policy behavior
- journal entity validation
- exchange adapter request signing helpers without real secrets

Repository tests:
- persist decision journal rows
- idempotent duplicate cycle handling
- update execution result
- summarize by action, risk status, execution status, and mode

Service tests:
- no prediction results in hold and journal row
- buy decision rejected by insufficient balance
- dry-run approved buy does not submit an order
- Spot Demo approved buy calls exchange adapter
- exchange failure is journaled as failed execution

Manual smoke tests:

```bash
uv run capm agent run-once \
  --symbol BTCUSDT \
  --interval 1m \
  --mode dry-run
```

```bash
uv run capm agent journal summary \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2026-05-30T00:00:00Z \
  --end 2026-05-31T00:00:00Z
```

Spot Demo smoke test should only run after credentials are configured:

```bash
uv run capm agent run-once \
  --symbol BTCUSDT \
  --interval 1m \
  --mode spot-demo \
  --max-trade-usdt 10
```

## 18. Implementation Order
Recommended implementation order:

1. Add trading domain entities.
2. Add trading contracts.
3. Add `agent_decision_journal` database model and repository methods.
4. Add deterministic decision policy.
5. Add risk-control service.
6. Add trading-agent orchestration service.
7. Add dry-run CLI commands.
8. Add repository and service tests.
9. Add Binance Spot Demo adapter.
10. Add Spot Demo CLI path.
11. Add README usage docs.

Reason:
- dry-run proves the core loop without exchange risk
- Spot Demo adapter can be added after journal and risk behavior are stable
- scheduling should wait until `run-once` is reliable

## 19. Future Work
Future branches should add:
- scan-universe batch cycle across inventory and top-20 watchlist
- provider-specific prompt tuning and optional additional LLM adapters
- prompt and response journal for AI decisions
- durable external scheduler with persisted loop/job state
- account websocket stream for execution updates
- portfolio snapshots and realized PnL attribution
- strategy-level backtest replay using the same decision policy
- account-wide dashboard views for decision journals and risk events

## 19.1 Current Implementation Status
Implemented in the first dry-run foundation:
- trading-agent domain entities and contracts
- shared `agent_decision_journal` persistence and summary reads
- idempotent cycle writes
- deterministic threshold policy
- hard risk-control validation
- `capm agent run-once --mode dry-run`
- `capm agent journal summary`
- repository and service tests

Implemented in the LLM decision step:
- discover symbols dynamically from DB coinpairs that contain candles for the requested interval
- make one OpenAI-compatible chat-completions call for the available symbol set
- support OpenRouter by default with configurable base URL, API key, and model
- validate strict JSON actions for every requested symbol
- retry malformed LLM responses up to the configured attempt count
- journal the prompt, raw response, attempt count, and risk-gated result
- include latest indicators, recent candles, prediction age, and portfolio state in the prompt
- reject inconsistent action amounts, non-positive sizes, and confidence values outside `0..1`
- journal provider host, model, latency, and token usage when returned by the provider

Current practical scope:
- the local database currently determines the coin universe
- BTCUSDT can be the only available symbol during initial development
- a curated fixed multi-coin list can be introduced later without changing the LLM batch boundary

Implemented in the Spot Demo execution step:
- authenticated Spot Demo account balance reads
- HMAC SHA256 signing for Binance signed REST requests
- market buy by quote amount and market sell by base quantity
- hard refusal to submit through the live Binance REST host
- update `agent_decision_journal` with exchange order IDs, status, and raw response
- skip duplicate submission when a retried cycle already has an exchange result
- add explicit `capm spot-demo account` and confirmed `capm spot-demo test-market-buy` smoke-test commands
- cache exchange symbol filters before submission
- reject market buys below minimum notional values
- normalize market sell quantities to the allowed market step size
- persist the initial submit response before querying the latest order status
- reconcile the submitted order with signed `GET /api/v3/order`

Implemented in the closed-candle live-cycle step:
- add `capm agent run-live-once`
- acquire one PostgreSQL advisory lock per interval and closed-candle boundary
- fill missing closed candles through REST without ingesting the open candle
- recompute and persist the recent default indicator window
- settle prediction-journal rows whose target candles are now available
- resolve repeated `SYMBOL=PATH` production artifact mappings
- generate and journal one prediction per configured model artifact
- run each artifact prediction in an isolated worker process to avoid native ML runtime conflicts
- run one LLM decision batch after market state and predictions are current
- keep dry-run as the default and require explicit `--mode spot-demo` for Demo execution
- stop before prediction and trading when the closed-candle gap exceeds the configurable inline-recovery threshold
- stop when a production artifact file is older than the configurable freshness threshold
- default the inline-recovery threshold to `180` minutes and model freshness threshold to `3` days
- require explicit `--allow-large-gap-recovery` and `--allow-stale-models` overrides for non-production recovery checks

Implemented in the operational-risk step:
- derive persistent execution state from filled Spot Demo rows in `agent_decision_journal`
- calculate symbol-scoped FIFO daily realized PnL from persisted exchange quote quantities
- reject submission when `CAPM_TRADING_EMERGENCY_STOP=true` or `--emergency-stop` is passed
- reject submission after the daily realized-loss limit
- reject submission after the daily order-count limit
- enforce a cooldown between submitted orders
- reject orders that exceed the priced symbol-exposure limit
- journal operational rejections with machine-readable risk violations

Implemented in the continuous-scheduler step:
- add `capm agent run-loop`
- reuse all closed-candle live-cycle, artifact, recovery, and operational-risk arguments
- sleep until shortly after each candle boundary before running a cycle
- support `--max-cycles` for bounded smoke tests
- support bounded failure handling with `--stop-after-error-count`
- log each cycle as a structured JSON payload
- close LLM, market-data, and Spot Demo clients on exit

Implemented in the observability-report step:
- add `capm agent report`
- include latest candle and indicator readiness
- include recent prediction journal rows and recent agent decisions
- include prediction and decision summaries over a configurable lookback window
- include symbol-scoped operational-risk state
- derive current position quantity, average entry price, exposure, and unrealized PnL from filled Spot Demo journal rows
- optionally include stored LLM prompts and current Spot Demo balances

Implemented in the dashboard/API step:
- expose FastAPI endpoints for health, symbols, summary, chart data, decisions, predictions, positions, risk status, prompts, execution orders, and Spot Demo portfolio
- expose manual Spot Demo market buy/sell endpoints that require `confirm: true`
- expose run-once and live-cycle endpoints
- expose continuous loop start/stop/status/log endpoints
- expose dashboard-native controls for runtime mode, market-data mode, large-gap recovery, stale-model override, and risk settings
- expose recent Spot Demo execution orders with linked decision IDs, exchange order IDs, fill status, quote quantity, average price, realized PnL, commission, and raw order details
- render buy/sell/hold markers, realized PnL curve, position state, operational risk meters, model cards, and recent decision timeline in the React dashboard

Current valuation limitations:
- exposure, daily order count, cooldown, and realized PnL are symbol-scoped until account-wide multi-coin controls are added
- FIFO realized PnL does not convert commissions charged in third-party assets into USDT

## 20. Open Questions
Open questions before implementation:
- Should `hold` decisions be journaled for every symbol every minute in scheduled mode, or sampled to reduce storage?
- Should dry-run use simulated balances only, or optionally mirror Spot Demo balances without execution?
- Should first Spot Demo orders use market orders only, or limit orders at the current best bid/ask?
- What confidence value should statistical and return-regression models expose when they do not have calibrated probabilities?
- Should the initial deterministic policy use one best model, all latest model predictions, or a configured model allowlist?
