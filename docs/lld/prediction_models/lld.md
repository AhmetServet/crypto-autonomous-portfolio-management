# Prediction Models LLD

## 1. Purpose
This document describes the low-level design for the first forecasting-model slice in `src/capm`.

The module covers:
- implementation boundaries for ARIMA, Prophet, XGBoost, and LightGBM
- DB-backed dataset reads for raw `OHLCV` and persisted feature rows
- walk-forward experiment orchestration on historical data
- offline portfolio evaluation with Backtrader
- notebook-friendly experiment workflows that reuse production-oriented services
- model metrics, artifact outputs, and comparison rules for baseline selection

This document complements:
- `docs/requirements/requirements_analysis.md`
- `docs/implementation_design/design.md`
- `docs/lld/data_store/lld.md`
- `docs/lld/indicators/lld.md`
- `docs/lld/binance_spot_market_data/lld.md`

## 2. Scope
Included in scope:
- statistical baseline models based on DB-stored candle history
- tabular ML baseline models based on DB-stored feature rows
- shared training and evaluation contracts
- walk-forward historical evaluation and metric reporting
- deterministic prediction-to-signal mapping for offline strategy comparison
- Backtrader-based backtest execution over historical data already stored in PostgreSQL or TimescaleDB
- experiment notebooks and reproducible runner scripts under `experiments/`

Out of scope:
- LSTM, GRU, DRL, TFT, or Informer implementation
- live per-minute inference orchestration
- nightly scheduler integration
- paper trading or live order execution
- online learning in v1
- advanced experiment tracking infrastructure such as MLflow or Weights & Biases
- feature engineering logic implemented only inside notebooks

## 3. Design Drivers
The design is shaped by the following requirements and current repository state:
- ARIMA and Prophet are the required statistical baselines
- XGBoost and LightGBM are the required structured-data challenger models
- experiments must compare model quality on historical data using RMSE and MAPE
- the project timeline also expects strategy-level comparison against Buy & Hold
- historical candles must come from the database rather than repeated Binance reads
- derived features are persisted in the database and should be reused as the source of truth for ML inputs
- the existing repository already exposes storage-backed candle and feature reads through stable ports
- notebooks are useful for analysis, but reproducible experiment logic must live in normal Python modules

Operational drivers:
- CPU-efficient models should be prioritized first
- backtests must clearly state that fees and slippage are excluded unless later modeled
- model window size `N` is still an open tuning parameter and must remain configurable
- sliding-window retraining is the default design, while incremental comparison remains an evaluation concern

## 4. Module Layout
Target layout for the first implementation slice:

```text
src/capm/
├─ core/
│  └─ contracts/
│     ├─ market_data.py
│     ├─ features.py
│     └─ prediction.py
├─ domains/
│  └─ prediction/
│     ├─ __init__.py
│     ├─ entities.py
│     ├─ metrics.py
│     ├─ splits.py
│     ├─ signals.py
│     └─ errors.py
├─ models/
│  ├─ registry.py
│  ├─ statistical/
│  │  ├─ __init__.py
│  │  ├─ arima.py
│  │  └─ prophet_model.py
│  └─ ml/
│     ├─ __init__.py
│     ├─ xgboost_model.py
│     └─ lightgbm_model.py
└─ services/
   ├─ training/
   │  ├─ dataset_loader.py
   │  ├─ adapters.py
   │  ├─ experiment_runner.py
   │  └─ artifact_store.py
   └─ backtesting/
      ├─ backtrader_runner.py
      └─ strategy_adapter.py

experiments/
├─ notebooks/
├─ runners/
├─ configs/
└─ results/
```

Responsibilities by area:
- `core/contracts/prediction.py`
  - shared protocols for model fitting, prediction, dataset loading, and artifact persistence
- `domains/prediction/entities.py`
  - immutable prediction-domain objects such as forecast requests, evaluation outputs, and model run metadata
- `domains/prediction/splits.py`
  - walk-forward split definitions and validation rules
- `domains/prediction/metrics.py`
  - pure metric functions such as RMSE, MAPE, direction accuracy, and benchmark comparison helpers
- `domains/prediction/signals.py`
  - deterministic conversion from model forecasts into buy, sell, or hold signals for backtests
- `models/statistical/*`
  - thin wrappers around ARIMA and Prophet libraries
- `models/ml/*`
  - thin wrappers around XGBoost and LightGBM libraries
- `services/training/dataset_loader.py`
  - DB-backed reads for candle series and persisted feature rows
- `services/training/adapters.py`
  - transforms canonical DB results into statistical or tabular model inputs
- `services/training/experiment_runner.py`
  - orchestrates walk-forward fits, predictions, metric collection, and artifact output
- `services/backtesting/*`
  - converts experiment outputs into Backtrader-compatible simulations and reports
- `experiments/`
  - notebook and script entrypoints for exploratory work that call shared services instead of duplicating logic

This structure follows the repository's current pattern of keeping domain rules pure, storage behind contracts, and orchestration inside services.

## 5. Data Source And Storage Assumptions

### 5.1 Database-First Rule
This slice is explicitly database-first.

Rules:
- model training reads historical candles from the market-data repository
- tabular ML model training reads persisted feature rows from the feature repository or feature-window read port
- experiment runs must not hit Binance directly for historical datasets
- notebooks must reuse repository-backed loaders instead of querying raw tables ad hoc or recomputing indicators by default

Why:
- repeated exchange reads are slower and introduce avoidable variability
- the database is already the project's historical source of truth
- using persisted features keeps experiments aligned with the data available to future production inference flows

### 5.2 Raw And Derived Data Roles
The data-store design already separates raw candles and derived features:
- raw table: `coinpair_<id>_ohlcv`
- derived table: `coinpair_<id>_feature`

Usage by model family:
- ARIMA and Prophet consume univariate series built from stored `OHLCV`
- XGBoost and LightGBM consume tabular datasets assembled from stored feature rows plus aligned targets
- Backtrader consumes stored market data and experiment-generated signals or forecast-driven orders

### 5.3 Canonical Read Boundaries
The first implementation should reuse these existing boundaries:
- `MarketDataRepositoryPort.get_candles(...)`
- `FeatureRepositoryPort.get_indicator_batch(...)`
- `FeatureWindowReadPort.get_feature_rows(...)`
- `FeatureWindowReadPort.get_latest_complete_window(...)`

Preferred rule:
- statistical models use candle reads directly
- tabular models use canonical `FeatureRow` reads rather than rebuilding indicator payloads in model code
- feature recomputation remains available through `IndicatorPipelineService`, but it is not the default experiment path

## 6. Prediction Responsibilities

### 6.1 `domains.prediction`
Responsibilities:
- define forecasting concepts independent from third-party libraries
- define evaluation outputs and artifact metadata
- enforce split and horizon validation
- define a deterministic signal policy for backtests

Important boundary:
- this package must not import model libraries, SQLAlchemy, or Backtrader

### 6.2 `models.statistical`
Responsibilities:
- accept normalized univariate input series
- fit ARIMA or Prophet models
- emit forecast values in a shared contract shape
- expose library-specific configuration through validated parameter objects

Important boundary:
- model wrappers must not know about database tables or notebook execution

### 6.3 `models.ml`
Responsibilities:
- accept tabular feature matrices and aligned targets
- fit XGBoost or LightGBM models
- emit shared prediction outputs and feature-importance metadata when available

Important boundary:
- wrappers must not reach into feature JSON payloads directly; dataset shaping belongs in adapters or loaders

### 6.4 `services.training`
Responsibilities:
- load historical data through repository ports
- build train and validation splits
- adapt data to model-family-specific shapes
- fit models, generate predictions, compute metrics, and persist artifacts
- expose reusable entrypoints for notebooks and scripts

### 6.5 `services.backtesting`
Responsibilities:
- transform forecast outputs into deterministic signals
- build Backtrader data feeds from stored historical candles
- run strategy simulations and compute portfolio metrics
- compare portfolio outcomes against Buy & Hold

## 7. Domain Data Contracts

### 7.1 `ForecastRequest`
Represents one experiment or inference request for a specific model and dataset slice.

Fields:
- `symbol`
- `interval`
- `target_field`
- `window_size`
- `forecast_horizon`
- `start_time`
- `end_time`
- `model_name`
- `model_parameters`

Rules:
- `window_size` must be positive
- `forecast_horizon` must be positive
- the requested time range must contain enough history for the chosen model family
- `target_field` defaults to `close` in v1

### 7.2 `ForecastDataset`
Represents the canonical dataset loaded for one experiment slice.

Fields:
- `symbol`
- `interval`
- `rows`
- `target_field`
- `feature_names`
- `window_size`
- `forecast_horizon`

Notes:
- `rows` should be derived from DB-backed candles or DB-backed feature rows
- the dataset remains model-family-agnostic until an adapter reshapes it

### 7.3 `ForecastResult`
Represents one model output batch over a validation slice.

Fields:
- `symbol`
- `interval`
- `model_name`
- `prediction_times`
- `predicted_values`
- `actual_values`
- `forecast_horizon`
- `metadata`

Notes:
- `metadata` may include fitted-parameter summaries, runtime, and feature-importance references
- actuals and predictions must align exactly by timestamp

### 7.4 `EvaluationReport`
Represents the metric output of one experiment run.

Fields:
- `symbol`
- `interval`
- `model_name`
- `split_id`
- `rmse`
- `mape`
- `direction_accuracy`
- `fit_duration_seconds`
- `predict_duration_seconds`
- `artifact_paths`

Notes:
- RMSE and MAPE are required
- direction accuracy is recommended because forecasting usefulness in trading is not captured by error alone

### 7.5 `BacktestReport`
Represents strategy-level results for one model and experiment configuration.

Fields:
- `symbol`
- `interval`
- `model_name`
- `trade_count`
- `profit_factor`
- `max_drawdown`
- `sharpe_ratio`
- `sortino_ratio`
- `cumulative_return`
- `buy_and_hold_return`
- `notes`

Required labeling:
- reports must explicitly state whether fees and slippage are excluded

## 8. Dataset Adaptation Design

### 8.1 Statistical Model Adapter
ARIMA and Prophet need an ordered univariate series.

Input source:
- `MarketDataRepositoryPort.get_candles(...)`

Output shape:
- ordered timestamps
- one numeric target series such as `close`

V1 rule:
- use closed-candle values only
- no future leakage
- no feature JSON expansion for these models

### 8.2 Tabular Model Adapter
XGBoost and LightGBM need a matrix of explanatory variables and aligned targets.

Input source:
- `FeatureWindowReadPort.get_feature_rows(...)`
- optional future extension: read pre-materialized training views if they are introduced later

Output shape:
- `X`: rows of numeric feature columns derived from `FeatureRow`
- `y`: shifted future target aligned to `forecast_horizon`
- `timestamps`: validation and reporting alignment keys

V1 rules:
- only use feature rows marked ready for the required features
- reject incomplete windows rather than silently imputing missing features
- keep target generation outside notebook code and inside shared adapters

### 8.3 Target Definition
The first implementation should lock one default target and leave room for future extensions.

Default target:
- next-step `close` forecast at horizon `h`

Follow-up options:
- return prediction
- directional up or down classification
- thresholded expected move for trade filtering

## 9. Runtime Flow

### 9.1 Historical Forecast Evaluation Flow
1. A notebook or runner submits a `ForecastRequest`.
2. The dataset loader reads the requested candle range from DB.
3. If the selected model requires features, the loader also reads canonical feature rows from DB.
4. The split builder creates walk-forward train and validation slices.
5. The family-specific adapter reshapes each slice into statistical or tabular model input.
6. The selected model wrapper fits on the training slice.
7. The wrapper predicts on the validation slice.
8. Pure metric functions compute RMSE, MAPE, and direction metrics.
9. The artifact store writes metrics, config snapshots, and optional fitted-model files.
10. The runner emits an `EvaluationReport` for each split and an aggregate summary for the full experiment.

### 9.2 Backtest Flow
1. The experiment runner collects or loads forecast outputs over a historical validation range.
2. The signal policy converts forecasts into deterministic buy, sell, or hold actions.
3. The backtesting runner loads the corresponding historical candles from DB.
4. The Backtrader adapter feeds market data and model-driven signals into the simulation.
5. Portfolio metrics are computed and compared against Buy & Hold.
6. The run emits a `BacktestReport` and stores result artifacts.

### 9.3 Feature Recompute Flow
This is not the default experiment path, but it remains supported when needed.

Use cases:
- derived rows are missing for a symbol or interval
- feature definitions change
- coverage needs repair after data maintenance

Flow:
1. A repair or backfill command uses `IndicatorPipelineService`.
2. The pipeline reads stored candles from DB.
3. The pipeline recomputes and persists derived rows.
4. Experiments resume using the refreshed DB-backed feature dataset.

## 10. Experiment Workspace Design

### 10.1 Workspace Goals
`experiments/` is reserved for exploratory work that remains reproducible.

Rules:
- notebooks may visualize data, compare runs, and explore hyperparameters
- experiment business logic must live in importable Python modules, not only in notebook cells
- configs and outputs must be stored in predictable paths so runs can be revisited later

### 10.2 Suggested Structure
- `experiments/notebooks/`
  - EDA, metric comparison, and visualization notebooks
- `experiments/runners/`
  - small Python entrypoints that call `services/training/experiment_runner.py`
- `experiments/configs/`
  - YAML or JSON experiment definitions for symbols, intervals, horizons, and model parameters
- `experiments/results/`
  - metrics, plots, serialized predictions, and backtest summaries

### 10.3 Notebook Rules
Recommended usage:
- import shared dataset loaders and experiment runners
- persist chart-ready outputs in `experiments/results/`
- do not issue direct SQL queries that bypass the repository layer unless explicitly needed for diagnosis
- do not compute permanent experiment features only inside notebooks

## 11. Backtesting Design

### 11.1 Why Backtrader In V1
Backtrader is a good default for the first experiment slice because:
- it provides a fast way to translate model outputs into portfolio simulations
- it is sufficient for offline comparative experiments
- it avoids prematurely building a custom engine before baseline forecasting quality is known

### 11.2 Strategy Adapter Boundary
The Backtrader integration should be thin.

Responsibilities:
- accept timestamp-aligned historical candles
- accept timestamp-aligned model outputs or derived signals
- map them into a deterministic strategy without model-library-specific code inside Backtrader

Important boundary:
- Backtrader code must not know whether the signal came from ARIMA, Prophet, XGBoost, or LightGBM

### 11.3 V1 Signal Policy
Backtest results are only comparable if all models use the same signal rule.

Recommended v1 rule:
- `buy` when predicted next-step return is greater than a positive threshold
- `sell` when predicted next-step return is smaller than a negative threshold
- `hold` otherwise

Alternative rule for very early experiments:
- sign of predicted price delta only

The final rule should be fixed in config and recorded in artifacts for every run.

### 11.4 Metrics
Required portfolio metrics:
- trade count
- profit factor
- max drawdown
- cumulative return
- cumulative return vs Buy & Hold

Recommended metrics:
- Sharpe ratio
- Sortino ratio
- win rate

## 12. Dependency Strategy
The current project dependencies do not yet include model or notebook libraries.

Recommended optional dependency groups:
- `ml`
  - `statsmodels`
  - `prophet`
  - `xgboost`
  - `lightgbm`
  - `pandas`
  - `numpy`
- `notebooks`
  - `jupyter`
  - `ipykernel`
  - plotting libraries if later needed
- `backtest`
  - `backtrader`

Recommendation:
- keep these optional so the core ingestion and storage package remains lightweight
- document exact install and run commands once the dependencies are added

## 13. Testing Strategy
Planned automated coverage should include:
- split-builder tests for walk-forward boundaries and leakage prevention
- dataset-adapter tests for statistical and tabular shapes
- target-alignment tests for forecast horizon handling
- model-wrapper tests on small deterministic fixtures
- metric-function tests for RMSE, MAPE, and direction accuracy
- signal-policy tests for threshold behavior
- backtest adapter tests that verify deterministic strategy translation
- experiment-runner tests with mocked model wrappers and small in-memory datasets

Recommended command:
```bash
uv run python -m unittest discover -s tests -t . -v
```

## 14. Known Limitations
- v1 prioritizes single-target forecasting on one symbol and one interval at a time
- ARIMA and Prophet use only univariate history in this design
- feature rows are still stored as JSON payloads, which may become inefficient for larger experiment volumes
- no experiment tracking server is included
- Backtrader integration remains offline-only and does not guarantee parity with future live execution rules
- fee and slippage modeling are intentionally excluded unless added later

## 15. Next Implementation Steps
1. Add `docs/lld/prediction_mdoels/lld.md` to the documentation index if a doc index is later introduced.
2. Introduce `core/contracts/prediction.py` with shared fit, predict, and dataset-loading protocols.
3. Add dataset loaders that read candles and canonical feature rows through existing repository ports.
4. Implement ARIMA and Prophet first to establish the baseline metric and artifact flow.
5. Implement XGBoost and LightGBM on top of persisted feature rows and shared target-generation logic.
6. Add experiment runners and config-driven notebooks under `experiments/`.
7. Integrate Backtrader through a thin strategy adapter and compare portfolio results against Buy & Hold.
8. Revisit storage shape if large-scale training makes JSON-backed feature reads too slow.
