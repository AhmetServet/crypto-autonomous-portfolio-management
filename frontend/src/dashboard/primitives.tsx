import type { ReactNode } from 'react'

import type { DataCoverageResponse } from '../api'
import { formatTime } from './format'

export function Metric({
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

export function Panel({
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

export function EmptyState({ message }: { message: string }) {
  return <div className="empty">{message}</div>
}

export function MutationResult({ title, data, error }: { title: string; data?: unknown; error?: Error | null }) {
  if (!data && !error) return null
  return (
    <div className="result-block">
      <h3>{title}</h3>
      <pre>{error ? error.message : JSON.stringify(data, null, 2)}</pre>
    </div>
  )
}

export function CoverageResult({ data }: { data?: DataCoverageResponse }) {
  if (!data) return null
  const rows = [
    ['OHLCV', data.ohlcv.covered_ranges.length, data.ohlcv.missing_ranges.length],
    ['Indicators', data.indicators.covered_ranges.length, data.indicators.missing_ranges.length],
    ['Features', data.features.covered_ranges.length, data.features.missing_ranges.length],
  ] as const
  return (
    <div className="coverage-block">
      {rows.map(([label, covered, missing]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{covered} covered / {missing} gaps</strong>
        </div>
      ))}
      {data.ohlcv.missing_ranges.length ? (
        <div className="coverage-detail">
          <span>First OHLCV Gap</span>
          <strong>{`${formatTime(data.ohlcv.missing_ranges[0].start)} -> ${formatTime(data.ohlcv.missing_ranges[0].end)}`}</strong>
        </div>
      ) : null}
    </div>
  )
}
