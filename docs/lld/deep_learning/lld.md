# Deep Learning Models LLD

## 1. Purpose
This document describes the low-level design for adding LSTM and GRU forecasting models to `src/capm`.

The module covers:
- sequence-window construction from persisted OHLCV and feature rows
- normalization and target alignment for recurrent neural networks
- LSTM and GRU wrapper responsibilities
- offline training, evaluation, artifact output, and runtime prediction integration
- comparison rules against ARIMA and Prophet baselines
- constraints for future per-minute inference and nightly retraining

This document complements:
- `docs/requirements/requirements_analysis.md`
- `docs/project_timeline/timeline[tr].md`
- `docs/implementation_design/design.md`
- `docs/lld/prediction_models/lld.md`
- `docs/lld/indicators/lld.md`
- `docs/lld/data_store/lld.md`

## 2. Requirement And Timeline Alignment
Requirements that directly shape this slice:
- LSTM and GRU are the layer-3 prediction models for sequential dependencies and long-range patterns.
- Model input is assembled from the latest `N` feature rows per coin.
- Window size `N` is configurable per model.
- Normalization is configurable per model type and applied during feature-matrix construction, not stored in raw DB tables.
- All model signals must eventually fit the common per-coin signal shape consumed by the LLM agent.
- All enabled models must eventually run after each closed 1m candle within the minute-cycle budget.
- Nightly retraining runs at `00:00` using a sliding window as the primary strategy.
- Fixed random seeds are required for reproducibility.

Timeline success criterion:
- For the "Deep Learning Models (LSTM/GRU)" milestone, LSTM/GRU test-set MAPE must be lower than ARIMA/Prophet MAPE.

Current baseline context:
- ARIMA and Prophet already have DB-backed walk-forward runs and saved `trained_models.pkl` artifacts.
- Recent sparse BTCUSDT 1m baseline results:
  - ARIMA MAPE around `0.001099`
  - Prophet MAPE around `0.002599`
- Deep-learning evaluation must compare against these statistical baselines on the same symbol, interval, horizon, and test window before claiming milestone success.

## 3. Scope
Included in scope:
- LSTM and GRU wrappers for sequence-to-one forecasting
- sequence dataset builder over canonical `FeatureRow` data
- configurable feature list, window size, forecast horizon, target mode, and scaler
- train/validation/test split support for reproducible experiments
- production-style training that saves deployable model and preprocessing artifacts
- runtime prediction from a saved deep-learning artifact through the existing prediction runtime path
- Backtrader holdout evaluation using the same signal policy as other models
- experiment configs under `experiments/configs/`
- focused unit tests for sequence shaping, scaling, target alignment, artifact validation, and runtime prediction

Out of scope for this slice:
- DRL models
- TFT, Informer, or other transformer architectures
- online learning
- multi-symbol shared neural networks
- GPU-specific optimization
- model serving outside the existing CLI/runtime path
- exchange execution, paper trading, or LLM agent integration
- hyperparameter search frameworks beyond config-defined runs

## 4. Design Drivers
The design is shaped by:
- the existing DB-first training approach
- the current `FeatureRow` read model and indicator payloads
- the requirement that feature windows remain causal and closed-candle only
- the need to produce artifacts that can predict on demand, even if model quality is not yet high
- timeline pressure to compare LSTM/GRU MAPE against ARIMA/Prophet
- CPU-first development on a local or VPS environment
- future 1-minute inference latency constraints

Pragmatic decisions:
- start with sequence-to-one regression, not seq2seq forecasting
- support `target_mode = "price"` and `target_mode = "return"` to match the production tabular trainer
- use the same feature set currently used by XGBoost/LightGBM unless a config overrides it
- keep scaling parameters inside the saved artifact so inference uses exactly the training transform
- prefer a single framework initially; PyTorch is the recommended implementation target because it is lightweight for custom training loops and CPU-friendly

## 5. Target Module Layout
Target layout:

```text
src/capm/
├─ models/
│  └─ deep_learning/
│     ├─ __init__.py
│     ├─ base.py
│     ├─ lstm_model.py
│     └─ gru_model.py
└─ services/
   ├─ prediction_runtime.py
   └─ training/
      ├─ sequence_dataset.py
      ├─ deep_learning_trainer.py
      └─ production_trainer.py

experiments/
├─ configs/
│  ├─ train_lstm_production.example.json
│  ├─ train_gru_production.example.json
│  └─ compare_deep_learning.example.json
└─ results/
```

Responsibilities:
- `models/deep_learning/base.py`
  - shared PyTorch module helpers, deterministic seed setup, device selection, and tensor conversion boundaries
- `models/deep_learning/lstm_model.py`
  - LSTM network wrapper with `fit` and `predict` behavior for sequence inputs
- `models/deep_learning/gru_model.py`
  - GRU network wrapper with the same public contract as LSTM
- `services/training/sequence_dataset.py`
  - converts ordered `FeatureRow` records into normalized sequence tensors and aligned targets
- `services/training/deep_learning_trainer.py`
  - trains one LSTM/GRU artifact, evaluates holdout metrics, runs optional Backtrader evaluation, and writes artifacts
- `services/prediction_runtime.py`
  - loads deep-learning artifacts, validates feature/scaler/window compatibility, builds the latest sequence, and emits normalized prediction payloads
- `experiments/configs/*`
  - reproducible configs for LSTM, GRU, and comparative runs

Registry changes:
- add model names `lstm` and `gru`
- add a new model family, likely `deep_learning`
- keep old statistical and tabular behavior unchanged

## 6. Data Source And Window Contract
Deep-learning models use the canonical DB-backed feature rows:
- source: `FeatureWindowReadPort.get_feature_rows(...)`
- latest inference: `FeatureWindowReadPort.get_latest_complete_window(...)`
- raw target reference: `FeatureRow.candle.<target_field>`
- feature inputs: `FeatureRow.indicator_values` plus optional OHLCV fields if enabled by config

Sequence input shape:
```text
X: [samples, sequence_length, feature_count]
y: [samples]
```

Definitions:
- `sequence_length`: number of past feature rows consumed per prediction
- `forecast_horizon`: number of candles ahead to predict
- `reference_index`: index of the final row included in the input sequence
- `target_index = reference_index + forecast_horizon`

For one sample:
```text
input rows = rows[reference_index - sequence_length + 1 : reference_index + 1]
target row = rows[reference_index + forecast_horizon]
```

Rules:
- all input rows must be consecutive at the configured interval
- all input rows must be `is_feature_ready = True`
- every configured feature must be present and non-null
- target rows must exist inside the selected training/evaluation range
- no feature row after `reference_index` may be used in `X`
- no scaler may be fit using validation, test, or holdout rows

## 7. Feature Set
Default input features should start with the persisted indicator features already used by tabular production models:
- `sma_20_close`
- `ema_20_close`
- `rsi_14_close`
- `macd_12_26_9_line`
- `macd_12_26_9_signal`
- `macd_12_26_9_histogram`
- `bbands_20_2_middle`
- `bbands_20_2_upper`
- `bbands_20_2_lower`

Optional OHLCV inputs:
- `open`
- `high`
- `low`
- `close`
- `volume`
- `quote_asset_volume`
- `taker_buy_base_asset_volume`
- `taker_buy_quote_asset_volume`

Config should control whether OHLCV fields are included. The first implementation should include indicator features only by default to keep comparison with XGBoost/LightGBM straightforward.

## 8. Normalization
Normalization is required for LSTM/GRU and must be part of the training artifact.

Supported scaler modes:
- `zscore`
- `minmax`
- `none` for diagnosis only

Scaler contract:
- fit scalers on the training split only
- store scaler type and per-feature parameters in the artifact
- transform train, validation, test, holdout, and runtime inference rows with the same parameters
- reject runtime prediction if a required feature is missing or cannot be converted to float

Recommended default:
- `zscore` for features
- no target scaling for return targets
- optional target scaling only for price targets if experiments show instability

Reason:
- return targets are naturally small and reduce the need for target scaling
- price targets can drift across years and may make neural training less stable

## 9. Target Definition
Supported target modes should match the production tabular trainer:
- `price`: predict future target field value at horizon `h`
- `return`: predict `(future_close - current_close) / current_close` at horizon `h`

Default for production-style deep-learning configs:
- `target_field = "close"`
- `target_mode = "return"`
- `forecast_horizon = 15`

Runtime conversion:
- if target mode is `price`, predicted value is emitted directly
- if target mode is `return`, predicted future price is `reference_value * (1 + predicted_return)`
- emitted payload includes both `predicted_value` and `predicted_return`

Direction:
- direction is derived from predicted return for now
- true binary or three-class direction classification remains a future improvement shared with the broader prediction stack

## 10. Model Architecture
### 10.1 Shared Parameters
Common config fields:
- `sequence_length`
- `feature_names`
- `target_field`
- `target_mode`
- `forecast_horizon`
- `hidden_size`
- `num_layers`
- `dropout`
- `learning_rate`
- `batch_size`
- `max_epochs`
- `early_stopping_patience`
- `weight_decay`
- `seed`
- `device`

Default starting point:
```json
{
  "sequence_length": 240,
  "forecast_horizon": 15,
  "hidden_size": 64,
  "num_layers": 2,
  "dropout": 0.1,
  "learning_rate": 0.001,
  "batch_size": 512,
  "max_epochs": 20,
  "early_stopping_patience": 3,
  "target_mode": "return",
  "scaler": "zscore",
  "seed": 42
}
```

### 10.2 LSTM
Network shape:
```text
input sequence
  -> LSTM(input_size=feature_count, hidden_size, num_layers, dropout)
  -> final hidden state
  -> dense layer
  -> scalar output
```

Use case:
- longer sequential dependencies
- smoother temporal memory than GRU at slightly higher compute cost

### 10.3 GRU
Network shape:
```text
input sequence
  -> GRU(input_size=feature_count, hidden_size, num_layers, dropout)
  -> final hidden state
  -> dense layer
  -> scalar output
```

Use case:
- similar sequence modeling with fewer gates and usually lower CPU cost
- good first comparison against LSTM on VPS-like hardware

## 11. Training Flow
Production-style deep-learning training flow:
1. Load ready feature rows from DB for symbol, interval, and configured time range.
2. Infer or validate feature names.
3. Split rows into train, validation, and holdout/test ranges by timestamp.
4. Fit scalers on train rows only.
5. Build sequence datasets for train, validation, and holdout/test.
6. Train LSTM or GRU with deterministic seeds.
7. Use validation loss for early stopping.
8. Restore the best validation checkpoint.
9. Predict holdout/test samples.
10. Compute RMSE, MAPE, direction accuracy, fit duration, predict duration.
11. Run Backtrader evaluation over holdout predictions with the same threshold policy as other models.
12. Train or preserve the final deployable model according to config:
    - default: save the best model from train+validation evaluation if holdout is final
    - optional: refit on train+validation after model selection for deployment
13. Write artifacts under `experiments/results/<run_id>/`.

Artifact files:
- `model.pt` or model state dict inside `model.pkl`
- `model.pkl` with metadata and preprocessing payload
- `summary.json`
- optional `training_curve.json`

Recommended artifact payload:
- `artifact_kind = "deep_learning_sequence"`
- `model_name`
- `framework`
- `model_state`
- `model_parameters`
- `feature_names`
- `ohlcv_fields`
- `sequence_length`
- `target_field`
- `target_mode`
- `forecast_horizon`
- `scaler`
- `trained_through`
- `validation_metrics`
- `fit_detail`

## 12. Evaluation Rules
Minimum evaluation metrics:
- RMSE
- MAPE
- direction accuracy
- fit duration
- predict duration
- Backtrader cumulative return
- Buy & Hold return over the same holdout window

Timeline acceptance comparison:
- LSTM/GRU MAPE must be compared against ARIMA/Prophet MAPE on the same:
  - symbol
  - interval
  - target field
  - forecast horizon
  - test window
  - prediction timestamps, where feasible

Pass condition for milestone:
- at least one of LSTM or GRU has lower test MAPE than both ARIMA and Prophet on the agreed test window

Stronger engineering gate:
- lower MAPE than ARIMA/Prophet
- direction accuracy at or above statistical baselines
- Backtrader result not materially worse than Buy & Hold after commission assumptions
- inference latency comfortably below the per-minute budget

Important caveat:
- lower MAPE alone does not imply a profitable trading signal
- the timeline criterion is a forecasting milestone, not a trading-readiness guarantee

## 13. Runtime Prediction Flow
Deep-learning runtime prediction should extend the existing `capm predict` command.

Expected command:
```bash
uv run capm predict \
  --model-artifact experiments/results/<run_id>/model.pkl \
  --symbol BTCUSDT \
  --interval 1m
```

Flow:
1. Load deep-learning artifact.
2. Validate `artifact_kind`, feature names, sequence length, scaler parameters, target mode, and horizon.
3. Read the latest complete feature window with `sequence_length` rows, or the sequence ending at `--at`.
4. Convert features into `[1, sequence_length, feature_count]`.
5. Apply saved scaler.
6. Run model in evaluation mode.
7. Convert return target to predicted price when needed.
8. Emit the existing normalized runtime prediction payload.

Failure behavior:
- missing feature rows: return a clear error and skip the symbol in future per-minute orchestration
- incomplete window: return a clear error with gap reason if available
- model artifact mismatch: fail loudly rather than silently reshaping or imputing

## 14. CLI And Config Design
Recommended training CLI:
```bash
uv run capm-train-deep-learning --config experiments/configs/train_lstm_production.example.json
```

Comparison CLI:
```bash
uv run capm-train-deep-learning --config experiments/configs/compare_deep_learning.example.json
```

Config shape:
```json
{
  "symbol": "BTCUSDT",
  "interval": "1m",
  "model_name": "lstm",
  "start_time": "2023-03-24T14:00:00Z",
  "validation_time": "2026-03-25T00:00:00Z",
  "split_time": "2026-04-25T00:00:00Z",
  "end_time": "2026-05-25T21:49:00Z",
  "target_field": "close",
  "target_mode": "return",
  "forecast_horizon": 15,
  "sequence_length": 240,
  "required_features": [],
  "scaler": "zscore",
  "model_parameters": {
    "hidden_size": 64,
    "num_layers": 2,
    "dropout": 0.1,
    "learning_rate": 0.001,
    "batch_size": 512,
    "max_epochs": 20,
    "early_stopping_patience": 3,
    "seed": 42
  },
  "backtest": {
    "starting_cash": 10000,
    "buy_threshold": 0.001,
    "commission_rate": 0.001,
    "cash_fraction": 0.95
  }
}
```

## 15. Dependency Strategy
Recommended optional dependency group:
```toml
[project.optional-dependencies]
deep-learning = [
    "torch",
    "numpy",
    "pandas"
]
```

Notes:
- `numpy` and `pandas` already exist in the `ml` optional group but should remain explicit or documented for this extra.
- Do not make PyTorch a core dependency; ingestion and storage must remain lightweight.
- GPU support is not required for the first implementation.
- If PyTorch install size is a concern on the target VPS, benchmark CPU-only wheels and document setup steps.

## 16. Testing Strategy
Automated coverage should include:
- sequence builder creates the correct `[samples, sequence_length, feature_count]` shape
- target alignment uses `reference_index + forecast_horizon`
- sequence builder rejects missing feature values
- scaler fits on train rows only and applies identical parameters at inference
- LSTM and GRU wrappers can overfit a tiny deterministic fixture
- training loop honors early stopping
- artifact save/load round trips preserve metadata and scaler state
- runtime prediction emits the same normalized payload shape as XGBoost/LightGBM
- invalid artifacts fail with actionable errors

Recommended command:
```bash
uv run python -m unittest discover -s tests -t . -v
```

## 17. Implementation Plan
1. Add the `deep-learning` optional dependency group.
2. Add `models/deep_learning` wrappers and register `lstm` and `gru`.
3. Add `services/training/sequence_dataset.py` for sequence construction and scaling.
4. Add deterministic tiny-fixture tests for sequence shaping and model wrappers.
5. Add `DeepLearningProductionTrainer`.
6. Add `capm-train-deep-learning` CLI.
7. Add LSTM, GRU, and comparison configs.
8. Extend `PredictionRuntimeService` for `artifact_kind = "deep_learning_sequence"`.
9. Run ARIMA/Prophet/LSTM/GRU on the same test window and report timeline acceptance status.
10. Update README and prediction docs with the final command set and results.

## 18. Known Limitations
- Initial LSTM/GRU models are single-symbol and single-interval.
- First implementation is sequence-to-one only.
- No attention mechanism or transformer baseline is included.
- No true classification target is included unless the broader prediction stack adds it first.
- No model-version registry table exists yet; artifacts remain filesystem-based.
- No prediction journal exists yet; runtime predictions are emitted as CLI JSON only.
- Performance on 50 coins and 5 years of 1m data is unproven and must be benchmarked before nightly multi-coin retraining.

## 19. Open Decisions
- Exact default `sequence_length`: start with `240`, but compare `60`, `240`, and `1440` if runtime permits.
- Whether OHLCV fields should be included with indicator features in the first benchmark.
- Whether final deployment artifact should refit on train+validation or preserve the best validation checkpoint.
- Whether to share the production tabular trainer interface or create a separate deep-learning trainer CLI.
- Whether to store model state in `model.pkl` only or keep `model.pt` beside JSON metadata.
