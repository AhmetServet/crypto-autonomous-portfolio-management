import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  Database,
  Eye,
  Play,
  RefreshCw,
  Shield,
  ShoppingCart,
  Wallet,
  X,
} from 'lucide-react'
import './App.css'
import {
  type AgentRunOnceRequest,
  type DashboardSummary,
  type DecisionRow,
  type FetchOhlcvRequest,
  type IngestOhlcvRequest,
  type JournalSummaryRequest,
  type LiveCycleRequest,
  type ModelArtifact,
  type PredictRequest,
  type PredictionRow,
  type SettlePredictionsRequest,
  fetchOhlcv,
  getDashboardSummary,
  getHealth,
  getModelArtifacts,
  getPrompt,
  getSpotDemoPortfolio,
  getSymbols,
  ingestOhlcv,
  initDatabase,
  runAgentOnce,
  runLiveCycleOnce,
  runPrediction,
  settlePredictions,
  submitSpotDemoMarketBuy,
  submitSpotDemoMarketSell,
  summarizeAgentJournal,
  summarizePredictionJournal,
} from './api'

const INTERVALS = ['1m', '5m', '15m', '1h']

function defaultStart() {
  return new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
}

function defaultEnd() {
  return new Date().toISOString()
}

function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value)
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `${formatNumber(value * 100, 2)}%`
}

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

function compactTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

function artifactLabel(artifact: ModelArtifact) {
  const trained = artifact.trained_through ? compactTime(artifact.trained_through) : compactTime(artifact.modified_at)
  return `${artifact.model_name} / ${artifact.artifact_kind} / trained ${trained} / acc ${formatPercent(artifact.direction_accuracy)} / return ${formatPercent(artifact.cumulative_return)}`
}

function statusClass(value: string | boolean | null | undefined) {
  if (value === true || value === 'ok' || value === 'approved' || value === 'filled' || value === 'up') return 'good'
  if (value === false || value === 'rejected' || value === 'failed' || value === 'down') return 'bad'
  return 'neutral'
}

function Metric({
  label,
  value,
  subvalue,
  icon,
}: {
  label: string
  value: string
  subvalue?: string
  icon: ReactNode
}) {
  return (
    <div className="metric">
      <div className="metric-head">
        {icon}
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      {subvalue ? <small>{subvalue}</small> : null}
    </div>
  )
}

function Panel({
  title,
  icon,
  children,
  action,
}: {
  title: string
  icon?: ReactNode
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          {icon}
          <h2>{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="empty">{message}</div>
}

function MutationResult({ title, data, error }: { title: string; data?: unknown; error?: Error | null }) {
  if (!data && !error) return null
  return (
    <div className="result-block">
      <h3>{title}</h3>
      <pre>{error ? error.message : JSON.stringify(data, null, 2)}</pre>
    </div>
  )
}

function DecisionsTable({
  rows,
  onOpenPrompt,
}: {
  rows: DecisionRow[]
  onOpenPrompt: (id: number) => void
}) {
  if (!rows.length) return <EmptyState message="No decisions found." />
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Action</th>
            <th>Risk</th>
            <th>Execution</th>
            <th>LLM</th>
            <th>Latency</th>
            <th>Reason</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{compactTime(row.reference_time)}</td>
              <td>
                <span className={`badge ${statusClass(row.action)}`}>{row.action}</span>
              </td>
              <td>
                <span className={`badge ${statusClass(row.risk_status)}`}>{row.risk_status}</span>
              </td>
              <td>{row.execution_status}</td>
              <td>{row.llm.model ?? '-'}</td>
              <td>{row.llm.latency_seconds ? `${formatNumber(row.llm.latency_seconds, 2)}s` : '-'}</td>
              <td className="truncate">{row.reason || '-'}</td>
              <td className="actions">
                <button type="button" className="icon-button" title="View prompt" onClick={() => onOpenPrompt(row.id)}>
                  <Eye size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PredictionsTable({ rows }: { rows: PredictionRow[] }) {
  if (!rows.length) return <EmptyState message="No predictions found." />
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Model</th>
            <th>Direction</th>
            <th>Pred Return</th>
            <th>Actual</th>
            <th>Settled</th>
            <th>Correct</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{compactTime(row.reference_time)}</td>
              <td>{row.model_name}</td>
              <td>
                <span className={`badge ${statusClass(row.predicted_direction)}`}>{row.predicted_direction}</span>
              </td>
              <td>{formatPercent(row.predicted_return)}</td>
              <td>{formatPercent(row.actual_return)}</td>
              <td>{row.settled_at ? compactTime(row.settled_at) : '-'}</td>
              <td>
                <span className={`badge ${statusClass(row.direction_correct)}`}>
                  {row.direction_correct === null ? 'pending' : row.direction_correct ? 'yes' : 'no'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RiskList({ summary }: { summary: DashboardSummary }) {
  const risk = summary.operational_risk
  const position = summary.position
  return (
    <div className="kv-grid">
      <div>
        <span>Position</span>
        <strong>{position.status}</strong>
      </div>
      <div>
        <span>Quantity</span>
        <strong>{formatNumber(position.quantity, 8)}</strong>
      </div>
      <div>
        <span>Avg Entry</span>
        <strong>{position.average_entry_price ? `$${formatNumber(position.average_entry_price, 2)}` : '-'}</strong>
      </div>
      <div>
        <span>Exposure</span>
        <strong>{position.current_exposure_usdt ? `$${formatNumber(position.current_exposure_usdt, 2)}` : '-'}</strong>
      </div>
      <div>
        <span>Unrealized PnL</span>
        <strong className={position.unrealized_pnl_usdt && position.unrealized_pnl_usdt < 0 ? 'text-bad' : 'text-good'}>
          {position.unrealized_pnl_usdt ? `$${formatNumber(position.unrealized_pnl_usdt, 2)}` : '-'}
        </strong>
      </div>
      <div>
        <span>Cooldown</span>
        <strong>{risk.cooldown_active ? 'active' : 'clear'}</strong>
      </div>
      <div>
        <span>Orders Today</span>
        <strong>{risk.orders_today}</strong>
      </div>
      <div>
        <span>Realized Today</span>
        <strong>{`$${formatNumber(risk.realized_pnl_today_usdt, 2)}`}</strong>
      </div>
    </div>
  )
}

function PromptDrawer({ journalId, onClose }: { journalId: number; onClose: () => void }) {
  const promptQuery = useQuery({
    queryKey: ['prompt', journalId],
    queryFn: () => getPrompt(journalId),
  })

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <header className="drawer-header">
          <div>
            <span>Decision #{journalId}</span>
            <h2>LLM Prompt</h2>
          </div>
          <button type="button" className="icon-button" title="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        {promptQuery.isLoading ? <EmptyState message="Loading prompt..." /> : null}
        {promptQuery.error ? <EmptyState message={promptQuery.error.message} /> : null}
        {promptQuery.data ? (
          <div className="prompt-blocks">
            <div>
              <h3>Provider</h3>
              <pre>{`${promptQuery.data.provider_host ?? '-'} / ${promptQuery.data.model ?? '-'}`}</pre>
            </div>
            <div>
              <h3>System</h3>
              <pre>{promptQuery.data.system_prompt ?? '-'}</pre>
            </div>
            <div>
              <h3>User</h3>
              <pre>{promptQuery.data.prompt ?? '-'}</pre>
            </div>
            <div>
              <h3>Raw Response</h3>
              <pre>{JSON.stringify(promptQuery.data.raw_response, null, 2)}</pre>
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  )
}

function DatabaseMarketControls({
  symbol,
  interval,
  onCompleted,
}: {
  symbol: string
  interval: string
  onCompleted: () => void
}) {
  const [symbolsText, setSymbolsText] = useState(symbol)
  const [marketSymbol, setMarketSymbol] = useState(symbol)
  const [marketInterval, setMarketInterval] = useState(interval)
  const [start, setStart] = useState(defaultStart())
  const [end, setEnd] = useState(defaultEnd())
  const [marketMode, setMarketMode] = useState<'demo' | 'live'>('demo')
  const [persistFetch, setPersistFetch] = useState(false)
  const [ingestSource, setIngestSource] = useState<'rest' | 'dump' | 'dump-with-rest-tail'>('dump-with-rest-tail')
  const [batchSize, setBatchSize] = useState(50000)

  const initMutation = useMutation({
    mutationFn: () => initDatabase({ symbols: symbolsText.split(',').map((item) => item.trim()).filter(Boolean) }),
    onSuccess: onCompleted,
  })
  const fetchMutation = useMutation({
    mutationFn: () => {
      const payload: FetchOhlcvRequest = {
        symbol: marketSymbol,
        interval: marketInterval,
        start,
        end,
        mode: marketMode,
        persist: persistFetch,
        batch_size: batchSize,
      }
      return fetchOhlcv(payload)
    },
    onSuccess: onCompleted,
  })
  const ingestMutation = useMutation({
    mutationFn: () => {
      const payload: IngestOhlcvRequest = {
        symbol: marketSymbol,
        interval: marketInterval,
        start,
        end,
        source: ingestSource,
        mode: marketMode,
        batch_size: batchSize,
      }
      return ingestOhlcv(payload)
    },
    onSuccess: onCompleted,
  })

  return (
    <Panel title="Database And Market Data" icon={<Database size={17} />}>
      <div className="control-grid three">
        <form className="control-form" onSubmit={(event) => { event.preventDefault(); initMutation.mutate() }}>
          <h3>Init DB</h3>
          <label>
            Symbols
            <input value={symbolsText} onChange={(event) => setSymbolsText(event.target.value)} />
          </label>
          <button type="submit" disabled={initMutation.isPending}>Initialize</button>
        </form>

        <form className="control-form wide" onSubmit={(event) => { event.preventDefault(); fetchMutation.mutate() }}>
          <h3>Fetch OHLCV</h3>
          <div className="form-grid">
            <label>Symbol<input value={marketSymbol} onChange={(event) => setMarketSymbol(event.target.value)} /></label>
            <label>Interval<input value={marketInterval} onChange={(event) => setMarketInterval(event.target.value)} /></label>
            <label>Mode<select value={marketMode} onChange={(event) => setMarketMode(event.target.value as 'demo' | 'live')}><option value="demo">demo</option><option value="live">live</option></select></label>
            <label>Batch<input type="number" min="1" value={batchSize} onChange={(event) => setBatchSize(Number(event.target.value))} /></label>
            <label>Start<input value={start} onChange={(event) => setStart(event.target.value)} /></label>
            <label>End<input value={end} onChange={(event) => setEnd(event.target.value)} /></label>
            <label className="check-row"><input type="checkbox" checked={persistFetch} onChange={(event) => setPersistFetch(event.target.checked)} />Persist fetched candles</label>
          </div>
          <button type="submit" disabled={fetchMutation.isPending}>Fetch</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); ingestMutation.mutate() }}>
          <h3>Ingest OHLCV</h3>
          <label>
            Source
            <select value={ingestSource} onChange={(event) => setIngestSource(event.target.value as 'rest' | 'dump' | 'dump-with-rest-tail')}>
              <option value="dump-with-rest-tail">dump-with-rest-tail</option>
              <option value="dump">dump</option>
              <option value="rest">rest</option>
            </select>
          </label>
          <button type="submit" disabled={ingestMutation.isPending}>Ingest</button>
        </form>
      </div>
      <MutationResult title="Init Result" data={initMutation.data} error={initMutation.error} />
      <MutationResult title="Fetch Result" data={fetchMutation.data} error={fetchMutation.error} />
      <MutationResult title="Ingest Result" data={ingestMutation.data} error={ingestMutation.error} />
    </Panel>
  )
}

function PredictionControls({
  symbol,
  interval,
  onCompleted,
}: {
  symbol: string
  interval: string
  onCompleted: () => void
}) {
  const [modelArtifact, setModelArtifact] = useState('experiments/results/<run_id>/model.pkl')
  const [referenceTime, setReferenceTime] = useState('')
  const [journalPrediction, setJournalPrediction] = useState(false)
  const [settleUntil, setSettleUntil] = useState('')
  const [settleLimit, setSettleLimit] = useState(1000)
  const [summaryStart, setSummaryStart] = useState(defaultStart())
  const [summaryEnd, setSummaryEnd] = useState(defaultEnd())
  const [modelName, setModelName] = useState('')

  const predictMutation = useMutation({
    mutationFn: () => {
      const payload: PredictRequest = {
        symbol,
        interval,
        model_artifact: modelArtifact,
        at: referenceTime.trim() || null,
        journal: journalPrediction,
      }
      return runPrediction(payload)
    },
    onSuccess: onCompleted,
  })
  const settleMutation = useMutation({
    mutationFn: () => {
      const payload: SettlePredictionsRequest = {
        symbol,
        interval,
        until: settleUntil.trim() || null,
        limit: settleLimit,
      }
      return settlePredictions(payload)
    },
    onSuccess: onCompleted,
  })
  const summaryMutation = useMutation({
    mutationFn: () => {
      const payload: JournalSummaryRequest = {
        symbol,
        interval,
        start: summaryStart,
        end: summaryEnd,
        model_name: modelName.trim() || null,
      }
      return summarizePredictionJournal(payload)
    },
  })

  return (
    <Panel title="Prediction Tools" icon={<BarChart3 size={17} />}>
      <div className="control-grid three">
        <form className="control-form wide" onSubmit={(event) => { event.preventDefault(); predictMutation.mutate() }}>
          <h3>Run Prediction</h3>
          <label>Model Artifact<input value={modelArtifact} onChange={(event) => setModelArtifact(event.target.value)} /></label>
          <label>Reference Time<input placeholder="optional ISO timestamp" value={referenceTime} onChange={(event) => setReferenceTime(event.target.value)} /></label>
          <label className="check-row"><input type="checkbox" checked={journalPrediction} onChange={(event) => setJournalPrediction(event.target.checked)} />Journal prediction</label>
          <button type="submit" disabled={predictMutation.isPending}>Predict</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); settleMutation.mutate() }}>
          <h3>Settle Predictions</h3>
          <label>Until<input placeholder="optional ISO timestamp" value={settleUntil} onChange={(event) => setSettleUntil(event.target.value)} /></label>
          <label>Limit<input type="number" min="1" value={settleLimit} onChange={(event) => setSettleLimit(Number(event.target.value))} /></label>
          <button type="submit" disabled={settleMutation.isPending}>Settle</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); summaryMutation.mutate() }}>
          <h3>Prediction Summary</h3>
          <label>Start<input value={summaryStart} onChange={(event) => setSummaryStart(event.target.value)} /></label>
          <label>End<input value={summaryEnd} onChange={(event) => setSummaryEnd(event.target.value)} /></label>
          <label>Model Name<input placeholder="optional" value={modelName} onChange={(event) => setModelName(event.target.value)} /></label>
          <button type="submit" disabled={summaryMutation.isPending}>Summarize</button>
        </form>
      </div>
      <MutationResult title="Prediction Result" data={predictMutation.data} error={predictMutation.error} />
      <MutationResult title="Settlement Result" data={settleMutation.data} error={settleMutation.error} />
      <MutationResult title="Prediction Summary Result" data={summaryMutation.data} error={summaryMutation.error} />
    </Panel>
  )
}

function AgentActionControls({
  symbol,
  interval,
  onCompleted,
}: {
  symbol: string
  interval: string
  onCompleted: () => void
}) {
  const [policy, setPolicy] = useState<'threshold' | 'llm'>('threshold')
  const [mode, setMode] = useState<'dry-run' | 'spot-demo'>('dry-run')
  const [showPrompt, setShowPrompt] = useState(false)
  const [dryRunUsdt, setDryRunUsdt] = useState(1000)
  const [dryRunBase, setDryRunBase] = useState(0)
  const [minReturn, setMinReturn] = useState(0.0005)
  const [agentSummaryStart, setAgentSummaryStart] = useState(defaultStart())
  const [agentSummaryEnd, setAgentSummaryEnd] = useState(defaultEnd())

  const runMutation = useMutation({
    mutationFn: () => {
      const payload: AgentRunOnceRequest = {
        symbol: policy === 'threshold' ? symbol : null,
        interval,
        mode,
        policy,
        show_prompt: showPrompt,
        dry_run_usdt_balance: dryRunUsdt,
        dry_run_base_asset_balance: dryRunBase,
        max_trade_usdt: 25,
        max_position_usdt: 100,
        min_predicted_return: minReturn,
        prediction_staleness_minutes: 5,
        emergency_stop: false,
        max_daily_realized_loss_usdt: 50,
        max_orders_per_day: 20,
        order_cooldown_minutes: 5,
        max_total_exposure_usdt: 100,
      }
      return runAgentOnce(payload)
    },
    onSuccess: onCompleted,
  })
  const summaryMutation = useMutation({
    mutationFn: () => summarizeAgentJournal({ symbol, interval, start: agentSummaryStart, end: agentSummaryEnd }),
  })

  return (
    <Panel title="Agent Actions" icon={<Activity size={17} />}>
      <div className="control-grid">
        <form className="control-form" onSubmit={(event) => { event.preventDefault(); runMutation.mutate() }}>
          <h3>Run Agent Once</h3>
          <div className="form-grid">
            <label>Policy<select value={policy} onChange={(event) => setPolicy(event.target.value as 'threshold' | 'llm')}><option value="threshold">threshold</option><option value="llm">llm</option></select></label>
            <label>Mode<select value={mode} onChange={(event) => setMode(event.target.value as 'dry-run' | 'spot-demo')}><option value="dry-run">dry-run</option><option value="spot-demo">spot-demo</option></select></label>
            <label>Dry USDT<input type="number" min="0" value={dryRunUsdt} onChange={(event) => setDryRunUsdt(Number(event.target.value))} /></label>
            <label>Dry Base<input type="number" min="0" value={dryRunBase} onChange={(event) => setDryRunBase(Number(event.target.value))} /></label>
            <label>Min Return<input type="number" step="0.0001" value={minReturn} onChange={(event) => setMinReturn(Number(event.target.value))} /></label>
            <label className="check-row"><input type="checkbox" checked={showPrompt} onChange={(event) => setShowPrompt(event.target.checked)} />Show LLM prompt</label>
          </div>
          <button type="submit" disabled={runMutation.isPending}>Run Agent</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); summaryMutation.mutate() }}>
          <h3>Agent Summary</h3>
          <label>Start<input value={agentSummaryStart} onChange={(event) => setAgentSummaryStart(event.target.value)} /></label>
          <label>End<input value={agentSummaryEnd} onChange={(event) => setAgentSummaryEnd(event.target.value)} /></label>
          <button type="submit" disabled={summaryMutation.isPending}>Summarize Agent</button>
        </form>
      </div>
      <MutationResult title="Agent Result" data={runMutation.data} error={runMutation.error} />
      <MutationResult title="Agent Summary Result" data={summaryMutation.data} error={summaryMutation.error} />
    </Panel>
  )
}

function App() {
  const queryClient = useQueryClient()
  const [interval, setInterval] = useState('1m')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [limit, setLimit] = useState(20)
  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(null)
  const [buyAmount, setBuyAmount] = useState(10)
  const [sellQuantity, setSellQuantity] = useState(0.0001)
  const [confirmBuy, setConfirmBuy] = useState(false)
  const [confirmSell, setConfirmSell] = useState(false)
  const [liveMode, setLiveMode] = useState<'dry-run' | 'spot-demo'>('dry-run')
  const [marketDataMode, setMarketDataMode] = useState<'demo' | 'live'>('demo')
  const [selectedModelArtifacts, setSelectedModelArtifacts] = useState<{ key: string; paths: string[] } | null>(null)
  const [allowLargeGapRecovery, setAllowLargeGapRecovery] = useState(false)
  const [allowStaleModels, setAllowStaleModels] = useState(false)

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30_000,
  })

  const symbolsQuery = useQuery({
    queryKey: ['symbols', interval],
    queryFn: () => getSymbols(interval),
  })

  const portfolioQuery = useQuery({
    queryKey: ['spot-demo-portfolio', symbol],
    queryFn: () => getSpotDemoPortfolio(symbol),
    refetchInterval: 30_000,
  })

  const summaryQuery = useQuery({
    queryKey: ['summary', symbol, interval, limit],
    queryFn: () => getDashboardSummary({ symbol, interval, limit, lookbackHours: 24 }),
    refetchInterval: 30_000,
  })

  const modelArtifactsQuery = useQuery({
    queryKey: ['model-artifacts', symbol, interval],
    queryFn: () => getModelArtifacts({ symbol, interval }),
    refetchInterval: 60_000,
  })

  const refreshOperationalData = () => {
    queryClient.invalidateQueries({ queryKey: ['summary'] })
    queryClient.invalidateQueries({ queryKey: ['spot-demo-portfolio'] })
    queryClient.invalidateQueries({ queryKey: ['model-artifacts'] })
  }

  const buyMutation = useMutation({
    mutationFn: () => submitSpotDemoMarketBuy({ symbol, usdt_amount: buyAmount, confirm: confirmBuy }),
    onSuccess: refreshOperationalData,
  })

  const sellMutation = useMutation({
    mutationFn: () => submitSpotDemoMarketSell({ symbol, quantity: sellQuantity, confirm: confirmSell }),
    onSuccess: refreshOperationalData,
  })

  const modelArtifactsResponse = modelArtifactsQuery.data
  const modelArtifacts = useMemo(() => modelArtifactsResponse?.artifacts ?? [], [modelArtifactsResponse])
  const latestModelArtifacts = useMemo(() => modelArtifactsResponse?.latest_by_model ?? [], [modelArtifactsResponse])
  const artifactSelectionKey = `${symbol}:${interval}`
  const effectiveSelectedModelArtifacts =
    selectedModelArtifacts?.key === artifactSelectionKey
      ? selectedModelArtifacts.paths
      : latestModelArtifacts.map((artifact) => artifact.artifact_path)

  const liveCycleMutation = useMutation({
    mutationFn: () => {
      const modelArtifacts = effectiveSelectedModelArtifacts.map((path) => `${symbol}=${path}`)
      const payload: LiveCycleRequest = {
        interval,
        mode: liveMode,
        model_artifacts: modelArtifacts,
        market_data_mode: marketDataMode,
        max_inline_gap_minutes: 180,
        max_model_age_days: 3,
        allow_large_gap_recovery: allowLargeGapRecovery,
        allow_stale_models: allowStaleModels,
        max_trade_usdt: 25,
        max_position_usdt: 100,
        emergency_stop: false,
        max_daily_realized_loss_usdt: 50,
        max_orders_per_day: 20,
        order_cooldown_minutes: 5,
        max_total_exposure_usdt: 100,
      }
      return runLiveCycleOnce(payload)
    },
    onSuccess: refreshOperationalData,
  })

  const symbols = symbolsQuery.data?.symbols.length ? symbolsQuery.data.symbols : [symbol]
  const summary = summaryQuery.data

  const latestDecision = summary?.recent_decisions[0]
  const latestPrice = summary?.position.current_price ?? null
  const modelCount = useMemo(() => {
    if (!summary) return 0
    return new Set(summary.recent_predictions.map((row) => row.model_name)).size
  }, [summary])

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">CAPM</p>
          <h1>Trading Dashboard</h1>
        </div>
        <div className="toolbar">
          <label>
            Symbol
            <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
              {symbols.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Interval
            <select value={interval} onChange={(event) => setInterval(event.target.value)}>
              {INTERVALS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Rows
            <input
              type="number"
              min="5"
              max="100"
              step="5"
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            />
          </label>
          <button type="button" className="refresh-button" onClick={() => summaryQuery.refetch()}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </header>

      {summaryQuery.error ? (
        <div className="error-banner">
          <AlertTriangle size={18} />
          <span>{summaryQuery.error.message}</span>
        </div>
      ) : null}

      <section className="metrics-grid">
        <Metric
          label="Latest Price"
          value={latestPrice ? `$${formatNumber(latestPrice, 2)}` : '-'}
          subvalue={summary?.market.latest_candle_time ? `Candle ${formatTime(summary.market.latest_candle_time)}` : 'No candle'}
          icon={<BarChart3 size={17} />}
        />
        <Metric
          label="Agent Decision"
          value={latestDecision?.action ?? '-'}
          subvalue={latestDecision ? `${latestDecision.risk_status} / ${latestDecision.execution_status}` : 'No decision'}
          icon={<Activity size={17} />}
        />
        <Metric
          label="Prediction Accuracy"
          value={formatPercent(summary?.prediction_summary.direction_accuracy)}
          subvalue={`${summary?.prediction_summary.settled_count ?? 0} settled / ${summary?.prediction_summary.prediction_count ?? 0} total`}
          icon={<Database size={17} />}
        />
        <Metric
          label="Models"
          value={String(modelCount)}
          subvalue={`Generated ${formatTime(summary?.generated_at)}`}
          icon={<Clock size={17} />}
        />
        <Metric
          label="API Health"
          value={healthQuery.data?.status ?? '-'}
          subvalue={healthQuery.data ? `DB ${healthQuery.data.database}` : 'Checking'}
          icon={<Database size={17} />}
        />
      </section>

      <div className="main-grid">
        <Panel title="Position And Risk" icon={<Shield size={17} />}>
          {summary ? <RiskList summary={summary} /> : <EmptyState message="Loading risk state..." />}
        </Panel>

        <Panel title="Market State" icon={<Wallet size={17} />}>
          {summary ? (
            <div className="kv-grid">
              <div>
                <span>Indicator Ready</span>
                <strong>{summary.market.indicator_ready ? 'yes' : 'no'}</strong>
              </div>
              <div>
                <span>Latest Indicator</span>
                <strong>{formatTime(summary.market.latest_indicator_time)}</strong>
              </div>
              <div>
                <span>Open</span>
                <strong>{summary.market.latest_candle ? `$${summary.market.latest_candle.open}` : '-'}</strong>
              </div>
              <div>
                <span>High</span>
                <strong>{summary.market.latest_candle ? `$${summary.market.latest_candle.high}` : '-'}</strong>
              </div>
              <div>
                <span>Low</span>
                <strong>{summary.market.latest_candle ? `$${summary.market.latest_candle.low}` : '-'}</strong>
              </div>
              <div>
                <span>Volume</span>
                <strong>{summary.market.latest_candle?.volume ?? '-'}</strong>
              </div>
            </div>
          ) : (
            <EmptyState message="Loading market state..." />
          )}
        </Panel>
      </div>

      <div className="main-grid">
        <Panel title="Spot Demo Portfolio" icon={<Wallet size={17} />}>
          {portfolioQuery.data ? (
            <div className="kv-grid">
              <div>
                <span>USDT Free</span>
                <strong>{`$${formatNumber(portfolioQuery.data.portfolio.available_usdt, 2)}`}</strong>
              </div>
              <div>
                <span>Base Free</span>
                <strong>{formatNumber(portfolioQuery.data.portfolio.base_asset_free, 8)}</strong>
              </div>
              <div>
                <span>Base Locked</span>
                <strong>{formatNumber(portfolioQuery.data.portfolio.base_asset_locked, 8)}</strong>
              </div>
              <div>
                <span>Source</span>
                <strong>{portfolioQuery.data.symbol}</strong>
              </div>
            </div>
          ) : (
            <EmptyState message={portfolioQuery.error ? portfolioQuery.error.message : 'Loading portfolio...'} />
          )}
        </Panel>

        <Panel title="Manual Spot Demo Orders" icon={<ShoppingCart size={17} />}>
          <div className="control-grid">
            <form
              className="control-form"
              onSubmit={(event) => {
                event.preventDefault()
                buyMutation.mutate()
              }}
            >
              <h3>Market Buy</h3>
              <label>
                USDT Amount
                <input type="number" min="0.01" step="0.01" value={buyAmount} onChange={(event) => setBuyAmount(Number(event.target.value))} />
              </label>
              <label className="check-row">
                <input type="checkbox" checked={confirmBuy} onChange={(event) => setConfirmBuy(event.target.checked)} />
                Confirm buy
              </label>
              <button type="submit" disabled={!confirmBuy || buyMutation.isPending}>
                Buy
              </button>
            </form>

            <form
              className="control-form"
              onSubmit={(event) => {
                event.preventDefault()
                sellMutation.mutate()
              }}
            >
              <h3>Market Sell</h3>
              <label>
                Quantity
                <input type="number" min="0.00000001" step="0.00000001" value={sellQuantity} onChange={(event) => setSellQuantity(Number(event.target.value))} />
              </label>
              <label className="check-row">
                <input type="checkbox" checked={confirmSell} onChange={(event) => setConfirmSell(event.target.checked)} />
                Confirm sell
              </label>
              <button type="submit" disabled={!confirmSell || sellMutation.isPending}>
                Sell
              </button>
            </form>
          </div>
          <MutationResult title="Buy Result" data={buyMutation.data} error={buyMutation.error} />
          <MutationResult title="Sell Result" data={sellMutation.data} error={sellMutation.error} />
        </Panel>
      </div>

      <Panel title="Run Agent Once" icon={<Play size={17} />}>
        <form
          className="run-form"
          onSubmit={(event) => {
            event.preventDefault()
            liveCycleMutation.mutate()
          }}
        >
          <div className="control-grid">
            <label>
              Trading Mode
              <select value={liveMode} onChange={(event) => setLiveMode(event.target.value as 'dry-run' | 'spot-demo')}>
                <option value="dry-run">dry-run</option>
                <option value="spot-demo">spot-demo</option>
              </select>
            </label>
            <label>
              Market Data
              <select value={marketDataMode} onChange={(event) => setMarketDataMode(event.target.value as 'demo' | 'live')}>
                <option value="demo">demo</option>
                <option value="live">live</option>
              </select>
            </label>
            <label className="check-row">
              <input type="checkbox" checked={allowLargeGapRecovery} onChange={(event) => setAllowLargeGapRecovery(event.target.checked)} />
              Allow large gap recovery
            </label>
            <label className="check-row">
              <input type="checkbox" checked={allowStaleModels} onChange={(event) => setAllowStaleModels(event.target.checked)} />
              Allow stale models
            </label>
          </div>
          <div className="artifact-selector">
            <div className="artifact-selector-head">
              <span>Model Artifacts</span>
              <button type="button" onClick={() => modelArtifactsQuery.refetch()} disabled={modelArtifactsQuery.isFetching}>
                <RefreshCw size={15} />
                Refresh Models
              </button>
            </div>
            {modelArtifactsQuery.error ? <div className="inline-error">{modelArtifactsQuery.error.message}</div> : null}
            {!modelArtifacts.length && !modelArtifactsQuery.error ? (
              <EmptyState message={modelArtifactsQuery.isFetching ? 'Loading trained models...' : 'No trained model artifacts found for this symbol and interval.'} />
            ) : (
              <div className="artifact-list">
                {modelArtifacts.map((artifact) => {
                  const selected = effectiveSelectedModelArtifacts.includes(artifact.artifact_path)
                  return (
                    <label key={artifact.artifact_path} className="artifact-option">
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={(event) => {
                          setSelectedModelArtifacts((current) => {
                            const currentPaths =
                              current?.key === artifactSelectionKey ? current.paths : effectiveSelectedModelArtifacts
                            if (event.target.checked) {
                              return {
                                key: artifactSelectionKey,
                                paths: currentPaths.includes(artifact.artifact_path)
                                  ? currentPaths
                                  : [...currentPaths, artifact.artifact_path],
                              }
                            }
                            return {
                              key: artifactSelectionKey,
                              paths: currentPaths.filter((path) => path !== artifact.artifact_path),
                            }
                          })
                        }}
                      />
                      <span>
                        <strong>{artifactLabel(artifact)}</strong>
                        <small>{artifact.artifact_path}</small>
                      </span>
                    </label>
                  )
                })}
              </div>
            )}
          </div>
          <button type="submit" disabled={!effectiveSelectedModelArtifacts.length || liveCycleMutation.isPending}>
            <Play size={15} />
            Run Once
          </button>
        </form>
        <MutationResult title="Run Result" data={liveCycleMutation.data} error={liveCycleMutation.error} />
      </Panel>

      <DatabaseMarketControls symbol={symbol} interval={interval} onCompleted={refreshOperationalData} />
      <PredictionControls symbol={symbol} interval={interval} onCompleted={refreshOperationalData} />
      <AgentActionControls symbol={symbol} interval={interval} onCompleted={refreshOperationalData} />

      <Panel title="Recent Decisions" icon={<Activity size={17} />}>
        <DecisionsTable rows={summary?.recent_decisions ?? []} onOpenPrompt={setSelectedPromptId} />
      </Panel>

      <Panel title="Recent Predictions" icon={<BarChart3 size={17} />}>
        <PredictionsTable rows={summary?.recent_predictions ?? []} />
      </Panel>

      {selectedPromptId !== null ? <PromptDrawer journalId={selectedPromptId} onClose={() => setSelectedPromptId(null)} /> : null}
    </main>
  )
}

export default App
