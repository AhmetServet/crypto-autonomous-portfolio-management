import { Activity, Bot, Gauge, Radio, Shield, Wallet } from 'lucide-react'

import type { DashboardSummary, DecisionRow, ModelArtifact } from '../api'
import { compactTime, formatNumber, formatPercent, modelStatus, statusClass } from './format'
import type { RiskSettings } from './risk-settings'

export function PositionHeroCard({ summary }: { summary?: DashboardSummary }) {
  const position = summary?.position
  const pnl = position?.unrealized_pnl_usdt ?? null
  const tone = pnl === null ? 'neutral' : pnl >= 0 ? 'good' : 'bad'
  return (
    <section className={`position-hero ${tone}`}>
      <div>
        <span className="panel-kicker"><Wallet size={14} /> Position</span>
        <strong>{position?.status ?? 'unknown'}</strong>
        <small>{position?.current_exposure_usdt ? `$${formatNumber(position.current_exposure_usdt, 2)} exposure` : 'No exposure'}</small>
      </div>
      <div>
        <span>Unrealized PnL</span>
        <strong>{pnl === null ? '-' : `${pnl >= 0 ? '+' : ''}$${formatNumber(pnl, 2)}`}</strong>
        <small>{formatPercent(position?.unrealized_pnl_pct)}</small>
      </div>
      <div>
        <span>Average Entry</span>
        <strong>{position?.average_entry_price ? `$${formatNumber(position.average_entry_price, 2)}` : '-'}</strong>
        <small>{position?.quantity ? `${formatNumber(position.quantity, 8)} base` : 'flat'}</small>
      </div>
    </section>
  )
}

export function LiveStatusBeacon({ latestDecision }: { latestDecision?: DecisionRow }) {
  const status = latestDecision?.execution_status ?? 'idle'
  const active = status !== 'idle' && status !== 'not_submitted'
  return (
    <section className="status-beacon">
      <div className={`beacon-dot ${active ? 'running' : 'idle'}`} />
      <div>
        <span className="panel-kicker"><Radio size={14} /> Live Agent</span>
        <strong>{latestDecision ? latestDecision.action : 'idle'}</strong>
        <small>{latestDecision ? `${compactTime(latestDecision.created_at)} / ${latestDecision.risk_status}` : 'No recent decision'}</small>
      </div>
    </section>
  )
}

export function RiskMeterPanel({ summary, settings }: { summary?: DashboardSummary; settings: RiskSettings }) {
  const exposure = summary?.position.current_exposure_usdt ?? 0
  const orders = summary?.operational_risk.orders_today ?? 0
  const dailyLoss = Math.max(0, -(summary?.operational_risk.realized_pnl_today_usdt ?? 0))
  return (
    <div className="risk-meter-grid">
      <RiskMeter label="Exposure" value={exposure} max={settings.maxExposureUsdt} format="money" />
      <RiskMeter label="Position" value={exposure} max={settings.maxPositionUsdt} format="money" />
      <RiskMeter label="Daily Loss" value={dailyLoss} max={settings.maxDailyLossUsdt} format="money" danger />
      <RiskMeter label="Orders" value={orders} max={settings.maxOrdersPerDay} />
    </div>
  )
}

function RiskMeter({ label, value, max, format, danger = false }: { label: string; value: number; max: number; format?: 'money'; danger?: boolean }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const tone = danger ? 'bad' : pct > 85 ? 'bad' : pct > 60 ? 'warn' : 'good'
  const formatted = format === 'money' ? `$${formatNumber(value, 2)} / $${formatNumber(max, 2)}` : `${formatNumber(value, 0)} / ${formatNumber(max, 0)}`
  return (
    <div className="risk-meter">
      <div><span>{label}</span><strong>{formatted}</strong></div>
      <div className="meter-track"><span className={tone} style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

export function ModelCards({ artifacts }: { artifacts: ModelArtifact[] }) {
  const activeArtifacts = artifacts.filter((artifact) => artifact.active && !artifact.archived).slice(0, 6)
  if (!activeArtifacts.length) return <div className="empty">No active model cards to show.</div>
  return (
    <div className="model-card-grid">
      {activeArtifacts.map((artifact) => (
        <article key={artifact.artifact_path} className={`model-card ${modelStatus(artifact)}`}>
          <div>
            <span className="panel-kicker"><Bot size={14} /> {artifact.model_type}</span>
            <strong>{artifact.model_name}</strong>
          </div>
          <div className="model-card-stats">
            <span>Accuracy <strong>{formatPercent(artifact.direction_accuracy)}</strong></span>
            <span>Return <strong>{formatPercent(artifact.cumulative_return)}</strong></span>
            <span>Trades <strong>{artifact.trade_count ?? '-'}</strong></span>
          </div>
          <small>{artifact.stale ? 'stale' : `trained ${compactTime(artifact.trained_through ?? artifact.modified_at)}`}</small>
        </article>
      ))}
    </div>
  )
}

export function DecisionTimeline({ decisions }: { decisions: DecisionRow[] }) {
  if (!decisions.length) return <div className="empty">No recent decisions for timeline.</div>
  return (
    <div className="decision-timeline">
      {decisions.slice(0, 12).map((decision) => (
        <div key={decision.id} className={`decision-node ${decision.action}`} title={decision.reason}>
          <span className={`timeline-dot ${decision.action}`} />
          <strong>{decision.action}</strong>
          <small>{compactTime(decision.created_at)}</small>
          <em className={`badge ${statusClass(decision.risk_status)}`}>{decision.risk_status}</em>
        </div>
      ))}
    </div>
  )
}

export function VisualSummaryRail({ summary, artifacts, settings }: { summary?: DashboardSummary; artifacts: ModelArtifact[]; settings: RiskSettings }) {
  return (
    <div className="visual-rail">
      <PositionHeroCard summary={summary} />
      <LiveStatusBeacon latestDecision={summary?.recent_decisions[0]} />
      <section className="visual-panel">
        <span className="panel-kicker"><Shield size={14} /> Risk Meters</span>
        <RiskMeterPanel summary={summary} settings={settings} />
      </section>
      <section className="visual-panel">
        <span className="panel-kicker"><Gauge size={14} /> Model Cards</span>
        <ModelCards artifacts={artifacts} />
      </section>
      <section className="visual-panel">
        <span className="panel-kicker"><Activity size={14} /> Decision Timeline</span>
        <DecisionTimeline decisions={summary?.recent_decisions ?? []} />
      </section>
    </div>
  )
}

export function SkeletonRows({ count = 4 }: { count?: number }) {
  return (
    <div className="skeleton-stack" aria-label="Loading">
      {Array.from({ length: count }).map((_, index) => <span key={index} />)}
    </div>
  )
}
