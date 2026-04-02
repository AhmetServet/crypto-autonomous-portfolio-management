# Indicator Module LLD

## 1. Purpose
This document describes the low-level design for the indicator and feature-engineering module that will power downstream ML inference and training.

The module covers:
- technical indicator computation on closed `1m` candles
- indicator configuration and built-in registry behavior
- persistence contracts for candle-aligned derived features
- canonical feature-window assembly for ML consumers
- warm-up, causality, and missing-data handling
- proposed package layout for the first implementation slice

This document complements:
- `docs/requirements/requirements_analysis.md`
- `docs/implementation_design/design.md`
- `docs/lld/data_store/lld.md`
- `docs/lld/binance_spot_market_data/lld.md`

## 2. Scope
Included in scope:
- computing SMA, EMA, RSI, MACD, and Bollinger Bands for each closed candle
- defining a stable feature contract aligned to `OHLCV`
- assembling the latest `N` candle-aligned feature rows for one symbol
- designing persistence keys and repository boundaries for feature rows
- defining warm-up and readiness semantics for ML-safe usage
- defining a hybrid-v1 extensibility approach based on configured built-in indicators

Out of scope:
- model-specific tensor shaping for individual model families
- normalization and scaling
- training-label generation
- exchange streaming orchestration
- database migrations and physical ORM implementation
- feature selection and importance analysis

## 3. Design Drivers
The design is shaped by the following requirements:
- indicators are computed after each closed candle for every coin in the scan universe
- feature rows must be time-aligned to raw `OHLCV`
- the latest `N` rows are assembled at inference time
- indicator parameters must be configurable
- the module must remain reusable across live inference, backfills, and future retraining jobs
- the module should support future config-driven extension without forcing a redesign in v1

ML-specific drivers:
- feature generation must be causal and deterministic
- warm-up behavior must be explicit
- feature names must remain stable across retraining cycles
- missing or incomplete windows must not silently degrade model quality

## 4. Module Layout
Target layout for the first implementation slice:

```text
src/capm/
├─ core/
│  └─ contracts/
│     ├─ market_data.py
│     └─ features.py
├─ domains/
│  └─ features/
│     ├─ __init__.py
│     ├─ entities.py
│     ├─ indicators.py
│     ├─ registry.py
│     ├─ windowing.py
│     └─ errors.py
└─ services/
   └─ features/
      └─ pipeline.py
```

Responsibilities by file:
- `core/contracts/features.py`
  - repository and read-model ports for derived feature persistence and window reads
- `domains/features/entities.py`
  - immutable feature-domain objects such as `IndicatorSpec`, `ComputedIndicatorSet`, `FeatureRow`, and `FeatureWindow`
- `domains/features/indicators.py`
  - pure computation functions for each built-in indicator
- `domains/features/registry.py`
  - config-backed registry that resolves enabled indicator specs to concrete computations
- `domains/features/windowing.py`
  - feature-row readiness rules and window assembly helpers
- `domains/features/errors.py`
  - feature-specific validation and data-gap exceptions
- `services/features/pipeline.py`
  - thin orchestration service that reads candles, computes features, persists derived rows, and builds canonical windows

This structure follows the existing patterns used by:
- `src/capm/domains/market_data/entities.py`
- `src/capm/core/contracts/market_data.py`
- `src/capm/services/ingestion/historical.py`

## 5. Domain Responsibilities

### 5.1 `domains.features`
Responsibilities:
- define canonical feature entities independent from storage
- compute indicators from ordered `OHLCV` series only
- enforce indicator-parameter validation
- define readiness and warm-up rules
- assemble causal time windows for downstream consumers

Important boundary:
- this package must not import storage or exchange adapters directly

### 5.2 `services.features.pipeline`
Responsibilities:
- load the required candle history for a symbol and interval
- invoke the indicator registry and calculator functions
- persist computed feature records through a port
- request canonical windows for inference or training callers
- return machine-readable statuses for insufficient history or data gaps

### 5.3 `core.contracts.features`
Responsibilities:
- abstract feature persistence and window reads behind stable interfaces
- keep domain and service logic independent from physical table layout
- allow the storage layer to evolve from simple tables to joins or materialized views later

## 6. Runtime Flow

### 6.1 Closed-Candle Computation Flow
1. A closed `1m` candle becomes available for a symbol.
2. The pipeline service determines the maximum lookback required by enabled indicators.
3. The service reads the needed `OHLCV` series from the market-data repository.
4. The service validates ordering, interval consistency, and candle continuity.
5. The indicator registry resolves the enabled built-in indicator specs.
6. Each indicator calculator computes values for the ordered series.
7. The service maps the results into one derived feature record per candle timestamp.
8. The feature repository upserts derived records keyed to the source candle.
9. The newest candle's feature readiness status is returned to the caller.

### 6.2 Canonical Window Assembly Flow
1. A downstream inference or training caller requests the latest `N` rows for one symbol and interval.
2. The pipeline reads raw candles plus aligned derived feature values through feature-aware repository ports.
3. The window builder merges raw and derived values into canonical `FeatureRow` objects.
4. The builder filters or rejects rows based on requested readiness policy.
5. If a fully usable window of length `N` exists, the builder returns `FeatureWindow`.
6. If the window is incomplete, the builder returns an explicit insufficiency or data-gap status for that symbol.

## 7. Domain Data Contracts

### 7.1 `IndicatorSpec`
Represents one configured built-in indicator.

Fields:
- `name`
- `kind`
- `parameters`
- `enabled`
- `source_field`
- `output_names`

Rules:
- `kind` must map to a built-in implementation in v1
- `parameters` must satisfy indicator-specific validation
- `output_names` must be deterministic and stable for the same spec
- `source_field` defaults to `close` unless the indicator explicitly supports another input

Example built-in specs:
- `sma_20_close`
- `ema_20_close`
- `rsi_14_close`
- `macd_12_26_9_close`
- `bbands_20_2_close`

### 7.2 `ComputedIndicatorSet`
Represents all computed indicator outputs for one candle.

Fields:
- `symbol`
- `interval`
- `open_time`
- `values`
- `is_ready`
- `missing_outputs`

Notes:
- `values` stores feature-name to decimal-or-null mappings
- `is_ready` is `True` only when all requested indicator outputs for that candle are available
- `missing_outputs` lists indicators still in warm-up for this timestamp

### 7.3 `FeatureRow`
Represents one canonical candle-aligned row used by ML consumers.

Fields:
- `symbol`
- `interval`
- `open_time`
- `close_time`
- raw candle fields copied from `OHLCV`
- `indicator_values`
- `is_feature_ready`

Notes:
- this is the canonical read model exposed to downstream code
- it combines raw `OHLCV` and derived indicator values
- it is row-oriented and does not encode model-specific shapes

### 7.4 `FeatureWindow`
Represents the latest causal `N` rows for one symbol.

Fields:
- `symbol`
- `interval`
- `rows`
- `window_size`
- `requested_features`
- `is_complete`
- `gap_reason`

Rules:
- rows must be ordered by `open_time ASC`
- rows must have consistent interval spacing
- `window_size == len(rows)`
- `is_complete` is `True` only when every row satisfies the caller's readiness policy

## 8. Indicator Computation Design

### 8.1 Supported Built-In Indicators
V1 supports:
- SMA
- EMA
- RSI
- MACD
- Bollinger Bands

Expected outputs:
- SMA: one output per configured period
- EMA: one output per configured period
- RSI: one output per configured period
- MACD: `line`, `signal`, `histogram`
- Bollinger Bands: `middle`, `upper`, `lower`, optional `bandwidth` later

### 8.2 Calculation Rules
All calculators must:
- accept an ordered `list[OHLCV]`
- return one output set per candle timestamp
- preserve decimal precision
- avoid storage or network side effects
- behave deterministically for the same input sequence

### 8.3 Warm-Up Policy
Indicators with insufficient lookback history do not fabricate values.

V1 rule:
- persist a derived record for every closed candle
- store `null` for outputs still warming up
- mark the candle `is_ready=False` when any enabled indicator output is missing

This allows:
- complete auditability of when a candle entered the system
- explicit readiness filtering for ML consumers
- idempotent recomputation after gap repair or backfills

## 9. Causality and ML Safety
The requirements did not formally lock causality rules, but this module should adopt a strict closed-candle contract by default.

Default rule:
- a feature row at time `t` may use data from candles with `open_time <= t` only
- no future candle may influence a feature row for an earlier timestamp

Implications:
- live inference and offline dataset generation can share the same feature code path
- label generation remains outside this module
- normalization remains outside this module
- downstream training code must decide how targets are shifted relative to feature rows

Recommended caller policy:
- use only `FeatureWindow.is_complete=True` windows for model input
- skip symbols with gaps or incomplete warm-up rather than padding silently

## 10. Persistence Strategy

### 10.1 Preferred V1 Shape
The implemented v1 persistence design uses a separate derived-feature store keyed one-to-one to raw candles.

Logical key:
- `symbol`
- `interval`
- `open_time`

Implemented physical direction:
- keep raw `OHLCV` storage as the source of truth in the existing market-data store
- persist indicator outputs in a separate symbol-scoped feature table named like `BTCUSDT_features`
- store indicator values in a JSON payload keyed by stable feature names
- store `is_ready` and `missing_outputs` beside the payload for ML-safe reads
- assemble canonical `FeatureRow` objects by merging raw candle data with aligned derived values at read time

Why this is preferred over adding columns directly to raw candle tables:
- new indicators or parameter changes should not require repeated schema churn
- derived features are recomputable and should stay isolated from raw market truth
- the design remains compatible with future config-driven extension
- repository ports can hide the join or view implementation from the domain layer

### 10.2 Repository Contract
Current ports in `core/contracts/features.py`:

- `FeatureRepositoryPort`
  - `save_indicator_batch(records) -> None`
  - `get_indicator_batch(symbol, interval, start_time, end_time) -> list[ComputedIndicatorSet]`
  - `get_indicator_set(symbol, interval, open_time) -> ComputedIndicatorSet | None`
  - `get_latest_indicator_time(symbol, interval) -> datetime | None`
  - `delete_indicator_batch(symbol, interval, start_time, end_time) -> int`

- `FeatureWindowReadPort`
  - `get_feature_rows(symbol, interval, start_time, end_time) -> list[FeatureRow]`
  - `get_latest_complete_window(symbol, interval, window_size, required_features) -> FeatureWindow | None`

Behavior:
- writes are idempotent by candle key
- reads return ordered results
- repositories can expose joined feature-row reads without materializing a separate training table
- repositories may implement joins, views, or denormalized caches internally without changing callers

### 10.3 Alignment Rules
Feature records must align exactly to the candle they were derived from:
- `symbol` must match the source `OHLCV.symbol`
- `interval` must match the source `OHLCV.interval`
- `open_time` identifies the candle and must remain stable across recomputation

If a candle is repaired or backfilled:
- recompute the affected lookback window
- upsert the derived rows for the affected timestamps

## 11. Window Assembly Contract

### 11.1 Canonical Output
The indicator module exposes a canonical row-oriented window only.

It does not:
- reshape rows into tensors
- flatten rows for tree models
- normalize or scale numeric values

These responsibilities belong to downstream inference and training modules.

### 11.2 Readiness Rule
Default v1 assembly behavior:
- a returned `FeatureWindow` must contain `N` consecutive rows
- every row must have all required indicator outputs available
- any missing candle or missing required indicator output makes the window incomplete

### 11.3 Missing Data Strategy
The module should degrade gracefully per symbol, not fail the whole cycle.

Preferred behavior:
- if one symbol has a gap or insufficient history, return a symbol-scoped incomplete result
- the caller can skip that symbol for the current cycle and log the reason
- the rest of the scan universe may continue

Machine-readable gap reasons should distinguish:
- insufficient history
- missing candle continuity
- missing derived feature rows
- partial warm-up

## 12. Naming and Versioning
Feature names must be stable and explicit.

Recommended naming pattern:
- `{kind}_{primary_parameters}_{source_field}`

Examples:
- `sma_20_close`
- `ema_50_close`
- `rsi_14_close`
- `macd_12_26_9_line`
- `macd_12_26_9_signal`
- `macd_12_26_9_histogram`
- `bbands_20_2_middle`
- `bbands_20_2_upper`
- `bbands_20_2_lower`

Versioning rule:
- treat the feature registry configuration as a versioned contract
- changing indicator parameters or output naming should produce a new feature-profile version in future model configs

## 13. Hybrid-V1 Extensibility Strategy
The requirements state that additional indicators should be addable via configuration without code changes. V1 will prepare for that outcome without over-designing the first slice.

V1 approach:
- support a config-defined list of built-in `IndicatorSpec` instances
- map each `kind` to a built-in implementation through `registry.py`
- allow parameter changes and enabled/disabled indicators entirely through config

Not in v1:
- user-defined formulas
- dynamic Python imports from config
- arbitrary dependency graphs between indicators

Future evolution path:
1. add a declarative expression layer for derived indicators
2. allow indicator composition from previously computed feature names
3. support validated plug-in registration at application startup

This keeps v1 safe and testable while preserving the path toward broader config-only extensibility.

## 14. Error Handling Strategy
Feature-specific exceptions should live in `domains/features/errors.py`.

Suggested error types:
- `FeatureValidationError`
- `IndicatorConfigurationError`
- `FeatureGapError`
- `IncompleteWindowError`

Rules:
- invalid indicator parameters fail during spec construction
- non-monotonic or interval-inconsistent candle series fail before computation
- incomplete windows return explicit statuses in read flows, not hidden partial success
- symbol-scoped failures should not abort unrelated symbols in the same minute cycle

## 15. Testing Strategy
Planned automated coverage should include:
- per-indicator unit tests for normal cases and edge cases
- warm-up behavior tests that confirm `null` output and readiness flags
- continuity validation tests for missing or duplicated candles
- registry tests for stable output naming from config
- window-builder tests for complete and incomplete `N`-row windows
- pipeline-service tests for symbol-scoped graceful degradation

Recommended command:
```bash
uv run python -m unittest discover -s tests -t . -v
```

## 16. Known Limitations
- v1 does not implement full config-defined custom indicators
- feature payloads are stored as JSON mappings rather than one typed DB column per indicator output
- cross-symbol feature queries are not optimized in this design
- normalization and label creation are intentionally deferred to downstream ML modules

## 17. Next Implementation Steps
1. add integration tests against PostgreSQL + TimescaleDB for raw and feature tables
2. version feature payloads explicitly once multiple model profiles are introduced
3. evaluate whether a materialized training read model is needed for large historical ML jobs
4. extend the example and future worker flows to recompute indicators automatically after gap repair and backfills
