import { BarChart3, Shield, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import type { DashboardSummary, HealthResponse } from '../api'
import { getPrompt } from '../api'
import { formatAge, formatNumber, formatTime } from './format'
import { EmptyState, Panel } from './primitives'

function readableJson(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  return JSON.stringify(value, null, 2)
}

function PromptSection({ title, children, kind = 'text' }: { title: string; children: string; kind?: 'text' | 'json' }) {
  return (
    <section className="prompt-section">
      <h3>{title}</h3>
      <pre className={`prompt-code ${kind}`}>{children || '-'}</pre>
    </section>
  )
}

export function RiskList({ summary }: { summary: DashboardSummary }) {
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

export function SystemHealthPanel({
  health,
  summary,
}: {
  health?: HealthResponse
  summary?: DashboardSummary
}) {
  const binance = health?.binance_demo
  const llm = health?.llm_provider
  return (
    <Panel title="System Health" icon={<Shield size={17} />}>
      <div className="kv-grid">
        <div>
          <span>API</span>
          <strong>{health?.api ?? health?.status ?? '-'}</strong>
        </div>
        <div>
          <span>Database</span>
          <strong>{health?.database ?? '-'}</strong>
        </div>
        <div>
          <span>Binance Demo</span>
          <strong>{binance?.status ?? '-'}</strong>
        </div>
        <div>
          <span>LLM Provider</span>
          <strong>{llm?.status ?? '-'}</strong>
        </div>
        <div>
          <span>LLM Model</span>
          <strong>{llm?.model ?? '-'}</strong>
        </div>
        <div>
          <span>Latest Candle Age</span>
          <strong>{formatAge(summary?.market.latest_candle_age_seconds)}</strong>
        </div>
        <div>
          <span>Latest Indicator Age</span>
          <strong>{formatAge(summary?.market.latest_indicator_age_seconds)}</strong>
        </div>
        <div>
          <span>Symbol Count</span>
          <strong>{health?.available_symbols_1m?.length ?? 0}</strong>
        </div>
      </div>
    </Panel>
  )
}

export function IndicatorsPanel({ summary }: { summary?: DashboardSummary }) {
  const indicators = Object.entries(summary?.market.indicators ?? {})
  return (
    <Panel title="Indicators" icon={<BarChart3 size={17} />}>
      {summary ? (
        <>
          <div className="kv-grid">
            <div>
              <span>Ready</span>
              <strong>{summary.market.indicator_ready ? 'yes' : 'no'}</strong>
            </div>
            <div>
              <span>Latest Indicator</span>
              <strong>{formatTime(summary.market.latest_indicator_time)}</strong>
            </div>
            <div>
              <span>Age</span>
              <strong>{formatAge(summary.market.latest_indicator_age_seconds)}</strong>
            </div>
            <div>
              <span>Missing Outputs</span>
              <strong>{summary.market.missing_indicator_outputs.length || '-'}</strong>
            </div>
          </div>
          {summary.market.missing_indicator_outputs.length ? (
            <div className="inline-note">{summary.market.missing_indicator_outputs.join(', ')}</div>
          ) : null}
          {indicators.length ? (
            <div className="indicator-grid">
              {indicators.map(([name, value]) => (
                <div key={name}>
                  <span>{name}</span>
                  <strong>{value ?? '-'}</strong>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState message="No indicators stored for the latest indicator timestamp." />
          )}
        </>
      ) : (
        <EmptyState message="Loading indicators..." />
      )}
    </Panel>
  )
}

export function PromptDrawer({ journalId, onClose }: { journalId: number; onClose: () => void }) {
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
            <section className="prompt-meta-panel" aria-label="Provider details">
              <div>
                <span>Provider</span>
                <strong>{promptQuery.data.provider_host ?? '-'}</strong>
              </div>
              <div>
                <span>Model</span>
                <strong>{promptQuery.data.model ?? '-'}</strong>
              </div>
              <div>
                <span>Latency</span>
                <strong>{promptQuery.data.latency_seconds === null ? '-' : `${promptQuery.data.latency_seconds}s`}</strong>
              </div>
              <div>
                <span>Symbol / Interval</span>
                <strong>{`${promptQuery.data.symbol ?? '-'} / ${promptQuery.data.interval ?? '-'}`}</strong>
              </div>
            </section>
            <PromptSection title="System">{promptQuery.data.system_prompt ?? '-'}</PromptSection>
            <PromptSection title="User" kind="json">
              {readableJson(promptQuery.data.prompt)}
            </PromptSection>
            <PromptSection title="Raw Response" kind="json">
              {readableJson(promptQuery.data.raw_response)}
            </PromptSection>
          </div>
        ) : null}
      </aside>
    </div>
  )
}
