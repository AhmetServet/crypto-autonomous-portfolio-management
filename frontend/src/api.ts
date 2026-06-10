const API_BASE_URL = import.meta.env.VITE_CAPM_API_BASE_URL ?? 'http://127.0.0.1:8000'

export type StatusCounts = Record<string, number>

export type Candle = {
  symbol: string
  interval: string
  open_time: string
  close_time: string
  open: string
  high: string
  low: string
  close: string
  volume: string
  trade_count: number
}

export type DashboardSummary = {
  status: string
  generated_at: string
  symbol: string
  interval: string
  lookback_hours: number
  market: {
    latest_candle_time: string | null
    latest_candle_age_seconds: number | null
    latest_candle: Candle | null
    latest_indicator_time: string | null
    latest_indicator_age_seconds: number | null
    indicator_ready: boolean | null
    missing_indicator_outputs: string[]
    indicators: Record<string, string | null>
  }
  operational_risk: {
    observed_at: string
    orders_today: number
    realized_pnl_today_usdt: number
    last_order_at: string | null
    next_order_allowed_at: string | null
    cooldown_active: boolean
  }
  position: {
    status: 'flat' | 'long'
    quantity: number
    cost_usdt: number
    average_entry_price: number | null
    current_price: number | null
    current_exposure_usdt: number | null
    unrealized_pnl_usdt: number | null
    unrealized_pnl_pct: number | null
  }
  prediction_summary: {
    prediction_count: number
    settled_count: number
    direction_accuracy: number | null
    mean_predicted_return: number | null
    predicted_direction_counts: StatusCounts
  }
  decision_summary: {
    decision_count: number
    action_counts: StatusCounts
    risk_status_counts: StatusCounts
    execution_status_counts: StatusCounts
    mode_counts: StatusCounts
  }
  recent_predictions: PredictionRow[]
  recent_decisions: DecisionRow[]
}

export type PredictionRow = {
  id: number
  model_name: string
  artifact_kind: string
  artifact_path: string
  reference_time: string
  prediction_time: string
  forecast_horizon: number
  target_mode: string
  reference_value: number
  predicted_value: number
  predicted_return: number
  predicted_direction: string
  actual_return: number | null
  actual_direction: string | null
  direction_correct: boolean | null
  settled_at: string | null
}

export type DecisionRow = {
  id: number
  created_at: string
  mode: string
  symbol: string
  interval: string
  reference_time: string
  action: string
  confidence: number | null
  reason: string
  requested_quantity: number | null
  requested_usdt_amount: number | null
  risk_violations: Array<Record<string, unknown>>
  risk_status: string
  execution_status: string
  exchange_order_id: string | null
  exchange_client_order_id: string | null
  exchange_response: Record<string, unknown>
  llm: {
    model: string | null
    provider_host: string | null
    latency_seconds: number | null
    attempts: number | null
    prompt?: string | null
    system_prompt?: string | null
    raw_response?: unknown
  }
}

export type SymbolsResponse = {
  status: string
  interval: string
  symbols: string[]
  symbol_statuses?: SymbolStatus[]
}

export type SymbolStatus = {
  symbol: string
  interval: string
  latest_candle_time: string | null
  latest_candle_age_seconds: number | null
  latest_indicator_time: string | null
  latest_indicator_age_seconds: number | null
  indicator_ready: boolean | null
  missing_indicator_outputs: string[]
}

export type PromptResponse = {
  status: string
  journal_id: number
  symbol: string
  interval: string
  model: string | null
  provider_host: string | null
  latency_seconds: number | null
  system_prompt: string | null
  prompt: string | null
  raw_response: unknown
}

export type HealthResponse = {
  status: string
  api?: string
  database: string
  available_symbols_1m?: string[]
  symbol_statuses_1m?: SymbolStatus[]
  binance_demo?: {
    status: string
    mode: string
    base_url: string
    api_key_configured: boolean
    api_secret_configured: boolean
    error?: string
  }
  llm_provider?: {
    status: string
    base_url: string
    model: string | null
    api_key_configured: boolean
  }
  error?: string
}

export type Portfolio = {
  available_usdt: number
  base_asset_free: number
  base_asset_locked: number
}

export type PortfolioResponse = {
  status: string
  symbol: string
  portfolio: Portfolio
}

export type ManualBuyRequest = {
  symbol: string
  usdt_amount: number
  confirm: boolean
}

export type ManualSellRequest = {
  symbol: string
  quantity: number
  confirm: boolean
}

export type ManualOrderResponse = {
  status: string
  symbol: string
  usdt_amount?: number
  quantity?: number
  portfolio_before: Portfolio
  order: Record<string, unknown>
  portfolio_after: Portfolio
}

export type LiveCycleRequest = {
  interval: string
  mode: 'dry-run' | 'spot-demo'
  model_artifacts: string[]
  market_data_mode: 'demo' | 'live'
  max_inline_gap_minutes: number
  max_model_age_days: number
  allow_large_gap_recovery: boolean
  allow_stale_models: boolean
  max_trade_usdt: number
  max_position_usdt: number
  emergency_stop: boolean
  max_daily_realized_loss_usdt: number
  max_orders_per_day: number
  order_cooldown_minutes: number
  max_total_exposure_usdt: number
}

export type LiveLoopRequest = LiveCycleRequest & {
  cycle_offset_seconds: number
  max_cycles: number | null
  stop_after_error_count: number
  sleep_after_error_seconds: number
  name?: string | null
}

export type LiveCycleResponse = {
  status: string
  cycle_time: string
  symbols: string[]
  ingested_candles: number
  persisted_indicators: number
  predictions_journaled: number
  predictions_settled: number
  skipped_reason: string | null
  decisions: Array<{
    cycle_id: string
    mode: string
    symbol: string
    interval: string
    action: string
    risk_status: string
    execution_status: string
    journal_id: number
  }>
}

export type LiveLoop = {
  id: string
  name: string
  status: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  return_code: number | null
  pid: number | null
  interval: string
  mode: string
  market_data_mode: string
  max_cycles: number | null
  cycle_offset_seconds: number
  log_path: string
  command: string[]
  log?: string
}

export type LiveLoopsResponse = {
  status: string
  loops: LiveLoop[]
}

export type LiveLoopResponse = {
  status: string
  loop: LiveLoop
}

export type ModelArtifact = {
  run_id: string
  symbol: string
  interval: string
  model_name: string
  model_type: string
  artifact_kind: string
  artifact_path: string
  summary_path: string
  trained_through: string | null
  modified_at: string
  direction_accuracy: number | null
  mape: number | null
  rmse: number | null
  cumulative_return: number | null
  trade_count: number | null
  active: boolean
  archived: boolean
  notes: string | null
  stale: boolean
}

export type ModelArtifactsResponse = {
  status: string
  results_dir: string
  artifacts: ModelArtifact[]
  latest_by_model: ModelArtifact[]
}

export type InitDatabaseRequest = {
  symbols: string[]
}

export type FetchOhlcvRequest = {
  symbol: string
  interval: string
  start: string
  end: string
  mode: 'demo' | 'live'
  persist: boolean
  batch_size: number
}

export type IngestOhlcvRequest = {
  symbol: string
  interval: string
  start: string
  end: string
  source: 'rest' | 'dump' | 'dump-with-rest-tail'
  mode: 'demo' | 'live'
  batch_size: number
}

export type DataRange = {
  start: string
  end: string
}

export type CoverageRange = {
  coinpair_id: number
  table_name: string
  symbol: string
  interval: string
  start: string
  end: string
}

export type DataCoverageResponse = {
  status: string
  symbol: string
  interval: string
  start: string
  end: string
  ohlcv: {
    covered_ranges: CoverageRange[]
    missing_ranges: DataRange[]
  }
  indicators: {
    covered_ranges: CoverageRange[]
    missing_ranges: DataRange[]
  }
  features: {
    covered_ranges: CoverageRange[]
    missing_ranges: DataRange[]
  }
}

export type RepairOhlcvGapsRequest = {
  symbol: string
  interval: string
  start: string
  end: string
  mode: 'demo' | 'live'
  batch_size: number
}

export type BackfillIndicatorsRequest = {
  symbol: string
  interval: string
  start: string
  end: string
  chunk_candle_count: number
  resume_from_latest: boolean
}

export type ModelArtifactStateRequest = {
  artifact_path: string
  active?: boolean | null
  archived?: boolean | null
  notes?: string | null
}

export type TrainingType = 'tabular' | 'deep_learning' | 'statistical'

export type TrainingPreset = {
  name: string
  path: string
  training_type: TrainingType
  symbol: string | null
  interval: string | null
  model_name: string | null
  description: string | null
  config: Record<string, unknown>
}

export type TrainingPresetsResponse = {
  status: string
  presets: TrainingPreset[]
}

export type TrainingJob = {
  id: string
  name: string
  training_type: TrainingType
  status: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  return_code: number | null
  pid: number | null
  config_path: string
  log_path: string
  command: string[]
  log?: string
}

export type TrainingJobsResponse = {
  status: string
  jobs: TrainingJob[]
}

export type TrainingJobResponse = {
  status: string
  job: TrainingJob
}

export type TrainingJobRequest = {
  training_type: TrainingType
  name?: string | null
  config: Record<string, unknown>
}

export type PredictRequest = {
  model_artifact: string
  symbol: string
  interval: string
  at: string | null
  journal: boolean
}

export type PredictBatchRequest = {
  model_artifacts: string[]
  symbol: string
  interval: string
  at: string | null
  journal: boolean
}

export type PredictionResult = {
  artifact_path: string
  artifact_kind: string
  model_name: string
  symbol: string
  interval: string
  reference_time: string
  prediction_time: string
  reference_value: number
  predicted_value: number
  predicted_return: number
  forecast_horizon: number
  target_mode: string
  feature_names: string[]
  metadata: Record<string, unknown>
  feature_window: {
    reference_time: string
    prediction_time: string
    forecast_horizon: number
    feature_names: string[]
    window_size: number
  }
  journal_id?: number
}

export type PredictResponse = {
  status: string
  prediction: PredictionResult
}

export type PredictBatchResponse = {
  status: string
  symbol: string
  interval: string
  reference_time: string | null
  success_count: number
  error_count: number
  results: Array<
    | { status: 'ok'; artifact_path: string; prediction: PredictionResult }
    | { status: 'error'; artifact_path: string; error_type: string; reason: string }
  >
}

export type SettlePredictionsRequest = {
  symbol: string
  interval: string
  until: string | null
  limit: number
}

export type JournalSummaryRequest = {
  symbol: string
  interval: string
  start: string
  end: string
  model_name?: string | null
}

export type AgentRunOnceRequest = {
  symbol: string | null
  interval: string
  mode: 'dry-run' | 'spot-demo'
  policy: 'threshold' | 'llm'
  show_prompt: boolean
  dry_run_usdt_balance: number
  dry_run_base_asset_balance: number
  max_trade_usdt: number
  max_position_usdt: number
  min_predicted_return: number
  prediction_staleness_minutes: number
  emergency_stop: boolean
  max_daily_realized_loss_usdt: number
  max_orders_per_day: number
  order_cooldown_minutes: number
  max_total_exposure_usdt: number
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${body}`)
  }
  return response.json() as Promise<T>
}

export function getHealth() {
  return fetchJson<HealthResponse>('/api/health')
}

export function getSymbols(interval: string) {
  return fetchJson<SymbolsResponse>(`/api/symbols?interval=${encodeURIComponent(interval)}`)
}

export function getDashboardSummary(params: {
  symbol: string
  interval: string
  limit: number
  lookbackHours: number
}) {
  const query = new URLSearchParams({
    symbol: params.symbol,
    interval: params.interval,
    limit: String(params.limit),
    lookback_hours: String(params.lookbackHours),
  })
  return fetchJson<DashboardSummary>(`/api/dashboard/summary?${query.toString()}`)
}

export function getPrompt(journalId: number) {
  return fetchJson<PromptResponse>(`/api/llm/prompts/${journalId}`)
}

export function getSpotDemoPortfolio(symbol: string) {
  return fetchJson<PortfolioResponse>(`/api/spot-demo/portfolio?symbol=${encodeURIComponent(symbol)}`)
}

export function getModelArtifacts(params: { symbol: string; interval: string; limit?: number }) {
  const query = new URLSearchParams({
    symbol: params.symbol,
    interval: params.interval,
    limit: String(params.limit ?? 100),
  })
  return fetchJson<ModelArtifactsResponse>(`/api/model-artifacts?${query.toString()}`)
}

export function updateModelArtifactState(request: ModelArtifactStateRequest) {
  return fetchJson<unknown>('/api/model-artifacts/state', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function getTrainingPresets() {
  return fetchJson<TrainingPresetsResponse>('/api/training/presets')
}

export function getTrainingJobs() {
  return fetchJson<TrainingJobsResponse>('/api/training/jobs')
}

export function getTrainingJob(jobId: string) {
  return fetchJson<TrainingJobResponse>(`/api/training/jobs/${jobId}`)
}

export function createTrainingJob(request: TrainingJobRequest) {
  return fetchJson<TrainingJobResponse>('/api/training/jobs', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function cancelTrainingJob(jobId: string) {
  return fetchJson<TrainingJobResponse>(`/api/training/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
}

export function submitSpotDemoMarketBuy(request: ManualBuyRequest) {
  return fetchJson<ManualOrderResponse>('/api/spot-demo/market-buy', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function submitSpotDemoMarketSell(request: ManualSellRequest) {
  return fetchJson<ManualOrderResponse>('/api/spot-demo/market-sell', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function runLiveCycleOnce(request: LiveCycleRequest) {
  return fetchJson<LiveCycleResponse>('/api/agent/run-live-once', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function getLiveLoops() {
  return fetchJson<LiveLoopsResponse>('/api/agent/loops')
}

export function getLiveLoop(loopId: string) {
  return fetchJson<LiveLoopResponse>(`/api/agent/loops/${loopId}`)
}

export function startLiveLoop(request: LiveLoopRequest) {
  return fetchJson<LiveLoopResponse>('/api/agent/loops', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function stopLiveLoop(loopId: string) {
  return fetchJson<LiveLoopResponse>(`/api/agent/loops/${loopId}/stop`, {
    method: 'POST',
  })
}

export function initDatabase(request: InitDatabaseRequest) {
  return fetchJson<unknown>('/api/database/init', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function fetchOhlcv(request: FetchOhlcvRequest) {
  return fetchJson<unknown>('/api/market/fetch-ohlcv', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function ingestOhlcv(request: IngestOhlcvRequest) {
  return fetchJson<unknown>('/api/market/ingest-ohlcv', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function getDataCoverage(params: { symbol: string; interval: string; start: string; end: string }) {
  const query = new URLSearchParams({
    symbol: params.symbol,
    interval: params.interval,
    start: params.start,
    end: params.end,
  })
  return fetchJson<DataCoverageResponse>(`/api/data/coverage?${query.toString()}`)
}

export function repairOhlcvGaps(request: RepairOhlcvGapsRequest) {
  return fetchJson<unknown>('/api/market/repair-ohlcv-gaps', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function backfillIndicators(request: BackfillIndicatorsRequest) {
  return fetchJson<unknown>('/api/features/backfill-indicators', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function runPrediction(request: PredictRequest) {
  return fetchJson<PredictResponse>('/api/predict', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function runPredictionBatch(request: PredictBatchRequest) {
  return fetchJson<PredictBatchResponse>('/api/predict/batch', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function settlePredictions(request: SettlePredictionsRequest) {
  return fetchJson<unknown>('/api/predictions/settle', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function summarizePredictionJournal(request: JournalSummaryRequest) {
  return fetchJson<unknown>('/api/prediction-journal/summary', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function runAgentOnce(request: AgentRunOnceRequest) {
  return fetchJson<unknown>('/api/agent/run-once', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function summarizeAgentJournal(request: JournalSummaryRequest) {
  return fetchJson<unknown>('/api/agent/journal/summary', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}
