import type { ModelArtifact } from '../api'

export const INTERVALS = ['1m', '5m', '15m', '1h']

export function defaultStart() {
  return new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
}

export function defaultEnd() {
  return new Date().toISOString()
}

export function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value)
}

export function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `${formatNumber(value * 100, 2)}%`
}

export function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

export function compactTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

export function formatAge(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '-'
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

export function artifactLabel(artifact: ModelArtifact) {
  const trained = artifact.trained_through ? compactTime(artifact.trained_through) : compactTime(artifact.modified_at)
  return `${artifact.model_name} / ${artifact.artifact_kind} / trained ${trained} / acc ${formatPercent(artifact.direction_accuracy)} / return ${formatPercent(artifact.cumulative_return)}`
}

export function modelStatus(artifact: ModelArtifact) {
  if (artifact.archived) return 'archived'
  if (!artifact.active) return 'inactive'
  if (artifact.stale) return 'stale'
  return 'active'
}

export function firstJsonValue(value: unknown) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

export function statusClass(value: string | boolean | null | undefined) {
  if (value === true || value === 'ok' || value === 'approved' || value === 'filled' || value === 'up') return 'good'
  if (value === false || value === 'rejected' || value === 'failed' || value === 'down') return 'bad'
  return 'neutral'
}
