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
    latest_candle: Candle | null
    latest_indicator_time: string | null
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
  reference_time: string
  prediction_time: string
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
  risk_status: string
  execution_status: string
  exchange_order_id: string | null
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

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${body}`)
  }
  return response.json() as Promise<T>
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
