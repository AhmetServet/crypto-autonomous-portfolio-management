# Requirements Analysis

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Coin Universe & Portfolio Rules](#2-coin-universe--portfolio-rules)
3. [Data Layer](#3-data-layer)
4. [Feature Engineering](#4-feature-engineering)
5. [Prediction Models](#5-prediction-models)
6. [LLM Agent](#6-llm-agent)
7. [Risk Control Layer](#7-risk-control-layer)
8. [Backtesting](#8-backtesting)
9. [Paper Trading](#9-paper-trading)
10. [User Interface](#10-user-interface)
11. [System Architecture](#11-system-architecture)
12. [Non-Functional Requirements](#12-non-functional-requirements)
13. [Open Items & Deferred Decisions](#13-open-items--deferred-decisions)

---

## 1. System Overview

The system is a fully autonomous, end-to-end portfolio management agent for Binance spot markets. It ingests real-time and historical market data, runs a multi-layered prediction pipeline, and delegates final trading decisions (including position sizing) to an LLM-based agent. The agent operates within a hard-rule risk control layer before any order reaches the exchange.

**Execution environment:** Personal VPS, 24/7  
**Exchange:** Binance Spot (Spot Demo Mode for paper trading, live for production)  
**Quote currency:** USDT  
**Candle interval:** 1 minute

---

## 2. Coin Universe & Portfolio Rules

### 2.1 Two-Tier Scanning Architecture

The system maintains two distinct coin sets that are unified at scan time.

**Tier 1 — Inventory Coins**

- Coins currently held in the portfolio.
- Always included in the per-minute scan regardless of watchlist status.
- Remain in the scan universe until fully sold, even if dropped from the top 20 list.
- Maximum 10 distinct coin types held simultaneously (hard constraint, enforced by the risk control layer, not the LLM).

**Tier 2 — Top 20 Watchlist**

- The 20 USDT pairs with the highest 24h trading volume on Binance.
- Updated nightly during the retraining window.
- All watchlist coins not currently in inventory are included in the per-minute scan.

**Effective scan universe per minute:**

```

scan_universe = union(inventory_coins, top20_watchlist)

# Maximum size: 10 (inventory) + 20 (watchlist) = 30, less on overlap

```

### 2.2 Portfolio Constraints

| Rule                                 | Value        | Enforced By          |
| ------------------------------------ | ------------ | -------------------- |
| Max distinct coin types in portfolio | 10           | Risk Control Layer   |
| Max coins in scan universe           | ~30          | System configuration |
| Position sizing                      | LLM decision | —                    |
| Concentration cap (single coin)      | None         | —                    |
| Adding to existing position          | Allowed      | —                    |

### 2.3 Coin List Lifecycle

- A coin dropped from the top 20 that is still held in inventory continues to be scanned and reported to the LLM.
- The LLM may choose to hold or sell it; no forced liquidation occurs at the system level.
- A coin is removed from the scan universe only when its inventory balance reaches zero and it is no longer in the top 20.

### 2.4 Initial Bootstrap Coins

Before the first top 20 refresh, the system starts with:

- BTC/USDT
- ETH/USDT
- BNB/USDT

---

## 3. Data Layer

### 3.1 Historical Data Ingestion

- Source: Binance REST API (`/api/v3/klines`)
- Coverage: Last 5 years of 1m OHLCV data per coin
- Pagination: Required due to Binance's per-request candle limit (max 1000 candles per call)
- Ingestion runs once per coin on initial setup; subsequent updates are handled by the nightly pipeline

### 3.2 Real-Time Data Ingestion

- Source: Binance WebSocket (`<symbol>@kline_1m`)
- Trigger: Each closed 1m candle fires an internal event
- The event initiates the full per-minute processing pipeline

### 3.3 Nightly Pipeline (00:00 daily)

1. Previous day's closed candles are appended to the training dataset.
2. Sliding window retraining is executed for all models.
3. Top 20 watchlist is refreshed based on updated 24h volume.
4. New coins entering the top 20 have their historical data backfilled if not already present.

### 3.4 Storage

- **Database:** PostgreSQL on the same VPS
- **Schema:** Partitioned by coin and date range (required for query performance at scale)
- **Estimated volume:** 50 coins × 5 years × 1m ≈ 130M rows on initial load

> **Note:** Disk capacity and PostgreSQL partition strategy must be planned before initial ingestion. Consider `PARTITION BY LIST (symbol)` combined with range sub-partitions by month.

### 3.5 Normalization

- Method: Min-Max or Z-score, configurable per model type
- Applied at feature matrix construction time, not stored in raw form

### 3.6 Fault Tolerance

- Automatic retry with exponential backoff on API errors
- If a coin's real-time stream is interrupted, the system logs the gap and resumes on reconnect
- Missing candles are backfilled from REST API before the next inference cycle

---

## 4. Feature Engineering

### 4.1 Technical Indicators

Computed automatically after each closed candle for every coin in the scan universe.

| Indicator                        | Signal                     |
| -------------------------------- | -------------------------- |
| Simple Moving Average (SMA)      | Trend direction            |
| Exponential Moving Average (EMA) | Trend direction (weighted) |
| Relative Strength Index (RSI)    | Overbought / oversold      |
| MACD                             | Momentum shift             |
| Bollinger Bands                  | Volatility range           |

Periods and parameters are configurable. Additional indicators can be added via configuration without code changes.

### 4.2 Feature Matrix

- Computed values are written to PostgreSQL alongside the raw OHLCV row
- The feature matrix for model input is assembled at inference time from the latest N rows per coin
- Window size (N) is a configurable parameter per model

---

## 5. Prediction Models

### 5.1 Model Stack

| Layer        | Models                                       | Purpose                                      |
| ------------ | -------------------------------------------- | -------------------------------------------- |
| 1            | ARIMA, Prophet                               | Trend and seasonality baseline               |
| 2            | XGBoost, LightGBM                            | Structured data, short-term patterns         |
| 3            | LSTM, GRU                                    | Sequential dependencies, long-range patterns |
| 4            | Deep Reinforcement Learning (DRL)            | Strategy learning via reward optimization    |
| 5 (optional) | Temporal Fusion Transformer (TFT) / Informer | Advanced comparative analysis                |

### 5.2 Model Output Format

Each model produces a per-coin signal passed to the LLM agent:

```json
{
    "coin": "BTC",
    "model": "LSTM",
    "signal": "buy",
    "confidence": 0.74,
    "predicted_direction": "up"
}
```

All model signals for all scanned coins are aggregated into a single structured payload before the LLM call.

### 5.3 Inference Execution

- All models run in parallel per coin after each closed candle
- Inference must complete within the 1-minute window before the next candle closes
- Models that fail to produce output within the time budget are skipped for that cycle and logged

### 5.4 Retraining Strategy

- **Method:** Sliding window (primary); incremental learning (tested in parallel)
- **Schedule:** Nightly at 00:00
- **Comparison:** Both strategies run simultaneously during the evaluation phase; the better-performing one is selected and the other is retired
- **DRL retraining:** Included in the nightly schedule. If DRL training consistently exceeds the nightly time window or degrades overall system performance, it is moved to a weekly schedule or disabled

> **Performance Note:** Retraining 30+ coins across 5+ model types nightly is computationally intensive, especially DRL on CPU. VPS specs must be benchmarked early. XGBoost and LightGBM are prioritized as they are CPU-efficient. DRL should be treated as optional from an operational standpoint.

---

## 6. LLM Agent

### 6.1 Role

The LLM agent is the sole decision-making unit. It receives the full system state and all model signals, then outputs a structured list of trading actions including position sizes. No voting, weighting, or rule-based aggregation of model signals is performed outside the LLM.

### 6.2 Service

- **Provider:** OpenRouter
- **Model:** Gemini Flash (or equivalent: large context window, low cost per token)
- **API key storage:** Environment variable, never hardcoded

### 6.3 Call Frequency

- Once per minute, triggered after all model inferences are complete
- One call covers all coins in the scan universe (single prompt, not per-coin calls)

### 6.4 Prompt Structure

```
[SYSTEM CONTEXT]
You are an autonomous portfolio management agent for Binance spot trading.
Your decisions are executed directly. Follow the output format exactly.

[PORTFOLIO STATE]
- Available USDT balance: {balance}
- Current holdings: [{coin, quantity, avg_cost, current_price, unrealized_pnl}, ...]
- Distinct coin types held: {count} / 10 maximum

[MARKET SIGNALS]
For each coin in scan universe:
- {coin}: price={current_price}, signals=[{model, signal, confidence}, ...]
  Last 5 candles: [{open, high, low, close, volume}, ...]

[RISK PARAMETERS]
- Max drawdown limit: {max_drawdown}%
- Max risk per trade: {risk_per_trade}%

[INSTRUCTIONS]
For each coin, decide: buy / sell / hold.
For buy/sell, specify the USDT amount.
Return only valid JSON. No explanation.

[OUTPUT FORMAT]
[
  {"coin": "BTC", "action": "buy", "usdt_amount": 500},
  {"coin": "ETH", "action": "hold", "usdt_amount": 0},
  {"coin": "SOL", "action": "sell", "usdt_amount": 200}
]
```

### 6.5 Response Handling

**Happy path:** JSON is parsed, each action is passed to the Risk Control Layer.

**Error path (invalid JSON or parse failure):**

1. Retry immediately with the original prompt plus an appended error message:
    ```
    [PREVIOUS RESPONSE ERROR]
    Your last response could not be parsed as valid JSON.
    Error: {parse_error_message}
    Return only valid JSON matching the specified format.
    ```
2. Up to 3 total attempts (1 original + 2 retries).
3. If all 3 attempts fail: no orders are placed for this cycle, event is logged with full prompt and response details.

### 6.6 Token Efficiency

- Prompt content must be compact. Candle history limited to last N candles (configurable, default: 5).
- Signal payload uses abbreviated keys to reduce token count.
- Monitor monthly token usage; adjust N or coin count if costs exceed budget.

---

## 7. Risk Control Layer

Sits between the LLM agent output and the order execution module. All rules are enforced at the system level and cannot be overridden by the LLM.

### 7.1 Hard Rules

| Rule                      | Condition                                                           | Action            |
| ------------------------- | ------------------------------------------------------------------- | ----------------- |
| Portfolio coin type limit | LLM orders a new coin but 10 distinct types already held            | Cancel order, log |
| Insufficient balance      | Required USDT exceeds available balance                             | Cancel order, log |
| Max drawdown breach       | Executing the order would push drawdown past the user-defined limit | Cancel order, log |
| Invalid coin              | Coin is not in scan universe (inventory or top 20)                  | Cancel order, log |
| Invalid action format     | Action is not buy / sell / hold                                     | Cancel order, log |
| Zero balance sell         | Sell order for a coin not in inventory                              | Cancel order, log |

### 7.2 Logging

Every cancelled order is written to a dedicated risk log with:

- Timestamp
- Coin
- Attempted action
- Rule violated
- LLM response snippet

---

## 8. Backtesting

- **Framework:** Custom backtesting engine (or adapted from Backtrader / Jesse)
- **Minimum simulated trades:** 1000
- **Data:** Historical candles from the PostgreSQL dataset (walk-forward or fixed split)
- **Slippage model:** Fill at Binance-returned price, no additional slippage modeled
- **Trading fees:** Not included

> **Academic Note:** Excluding fees and slippage will cause backtest results to diverge positively from real performance, particularly at 1m frequency with high trade counts. All reported results must be clearly labeled as "excluding fees and slippage." This should be stated explicitly in the project report and any publications.

### 8.1 Success Criteria

| Metric              | Threshold |
| ------------------- | --------- |
| Profit Factor       | > 1.0     |
| Max Drawdown        | < 30%     |
| Minimum trade count | ≥ 1000    |

### 8.2 Reported Metrics

- RMSE, MAPE (per model, prediction accuracy)
- Sharpe Ratio
- Sortino Ratio
- Profit Factor
- Max Drawdown
- Cumulative return vs. Buy & Hold benchmark

---

## 9. Paper Trading

- **Environment:** Binance Spot Demo Mode
- **Minimum autonomous orders:** 100
- **Pipeline:** Identical to production; only the Binance API base URL differs
- **Validation goals:**
    - Order execution succeeds without errors
    - Risk control layer functions correctly under live-like conditions
    - Latency per cycle (candle close → order sent) is measured and logged
    - System runs uninterrupted for a minimum of 7 consecutive days

---

## 10. User Interface

- **Framework:** React
- **Connection:** REST API calls to the FastAPI dashboard backend
- **Authentication:** Not specified (TBD)

### 10.1 Features

| Feature | Description |
| --- | --- |
| Core dashboard | Health, latest candle/indicator freshness, current market state, recent predictions, recent decisions, and Spot Demo portfolio view |
| Trading controls | Manual Spot Demo market buy/sell forms with explicit confirmation and raw order inspection |
| Data management | Database initialization, OHLCV fetch/ingest forms, coverage checks, missing candle repair, and indicator backfill |
| Training UI | Native training forms for tabular, deep-learning, and statistical model presets with job queue, logs, cancellation, and artifacts |
| Model registry | Active/inactive/archive controls, artifact metrics, model cards, stale warnings, and active model selection |
| Prediction runtime | Manual prediction, all-active prediction, exact error messages when data/features are missing, journal toggle, settlement, and summary |
| Risk controls | Emergency stop, max trade size, max position size, daily loss, orders/day, cooldown, exposure, and conservative/normal/aggressive presets |
| Agent controls | Run once, continuous live loop start/stop, runtime config, cycle logs, prompt inspection, and execution status |
| Execution view | Recent Spot Demo submitted orders, fill status, exchange IDs, linked decisions, realized PnL, and raw order drawer |
| Charts and visuals | Chart.js price/candlestick overlay, indicator detail, realized PnL curve, buy/sell/hold markers, position hero, live status beacon, risk meters, model cards, and decision timeline |

---

## 11. System Architecture

### 11.1 Stack

| Component          | Technology                           |
| ------------------ | ------------------------------------ |
| Backend            | Python modular monolith              |
| API layer          | FastAPI                              |
| Frontend           | React + Vite + Chart.js              |
| Database           | PostgreSQL                           |
| Hosting            | Personal VPS                         |
| Process management | systemd or Supervisor                |
| LLM provider       | OpenRouter                           |
| Exchange API       | Binance REST + WebSocket             |

### 11.2 Architectural Pattern

**Modular monolith with event-driven internal flow.**

- No microservices. Single backend package plus React dashboard.
- Internal events (e.g., candle closed) trigger processing stages in sequence.
- Suitable for expected traffic volume; microservices overhead is not justified.

### 11.3 Per-Minute Processing Flow

```
Binance WebSocket
  → Candle close event received
  → Feature engineering (parallel per coin)
  → Model inference (parallel per coin, all layers)
  → Signal aggregation
  → LLM agent call (single prompt)
      → On parse error: retry up to 3 times with error context
      → On 3 failures: skip cycle, log
  → Risk control layer (per order in LLM response)
  → Order execution (Binance API)
  → Write to log
```

### 11.4 Nightly Flow (00:00)

```
Top 20 watchlist refresh (Binance 24h volume)
  → Backfill historical data for new coins
  → Sliding window dataset update (all coins)
  → Model retraining (all layers, parallel where possible)
      → DRL: retrain if within time budget, else defer to weekly
  → Incremental learning run (parallel, for comparison)
  → Log retraining results and timing
```

### 11.5 Deployment Notes

- All API keys (Binance, OpenRouter) stored as environment variables
- PostgreSQL on same VPS; configure `max_connections` and `work_mem` appropriately for parallel query load
- systemd service with automatic restart on failure
- Log rotation configured to prevent disk exhaustion

---

## 12. Non-Functional Requirements

| Requirement     | Specification                                                                    |
| --------------- | -------------------------------------------------------------------------------- |
| Availability    | 24/7; auto-restart on process failure                                            |
| Fault tolerance | Retry with backoff on all external API calls                                     |
| Reproducibility | Fixed random seeds for all model training runs                                   |
| Extensibility   | Adding a new coin or model requires only configuration changes, not code changes |
| Security        | No secrets in source code or version control                                     |
| Observability   | All LLM calls, model signals, orders, and risk events are logged with timestamps |
| Spot Demo uptime | Minimum 7 consecutive days without manual intervention                          |

---

## 13. Open Items & Deferred Decisions

| #   | Item                                          | Notes                                                                                                                                          |
| --- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | UI authentication                             | Not defined. At minimum, the UI should not be publicly accessible without credentials given it controls live trading parameters.               |
| 2   | VPS specifications                            | CPU core count and RAM directly impact nightly retraining time. Must be benchmarked before DRL schedule is finalized.                          |
| 3   | PostgreSQL partition strategy                 | Partition by symbol (LIST) + month (RANGE) is the recommended approach but must be validated against actual query patterns.                    |
| 4   | Model input window size (N)                   | The number of past candles fed into each model is a critical hyperparameter. Initial value must be set before baseline experiments.            |
| 5   | Prompt token budget                           | Actual token count per prompt must be measured once model signal format is finalized. Adjust history window (N candles) accordingly.           |
| 6   | DRL algorithm selection                       | PPO, A3C, SAC — not yet decided. Selection should be based on a short comparative experiment before the nightly retraining schedule is locked. |
| 7   | Incremental vs. sliding window final decision | Deferred to experimental comparison during development phase.                                                                                  |
