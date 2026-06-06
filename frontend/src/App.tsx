import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  Database,
  Eye,
  RefreshCw,
  Shield,
  Wallet,
  X,
} from 'lucide-react'
import './App.css'
import {
  type DashboardSummary,
  type DecisionRow,
  type PredictionRow,
  getDashboardSummary,
  getPrompt,
  getSymbols,
} from './api'

const INTERVALS = ['1m', '5m', '15m', '1h']

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

function App() {
  const [interval, setInterval] = useState('1m')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [limit, setLimit] = useState(20)
  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(null)

  const symbolsQuery = useQuery({
    queryKey: ['symbols', interval],
    queryFn: () => getSymbols(interval),
  })

  const summaryQuery = useQuery({
    queryKey: ['summary', symbol, interval, limit],
    queryFn: () => getDashboardSummary({ symbol, interval, limit, lookbackHours: 24 }),
    refetchInterval: 30_000,
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
