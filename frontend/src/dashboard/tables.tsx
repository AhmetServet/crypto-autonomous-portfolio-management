import { Eye } from 'lucide-react'

import type { DecisionRow, PredictionRow } from '../api'
import { compactTime, firstJsonValue, formatNumber, formatPercent, statusClass } from './format'
import { EmptyState } from './primitives'

export function DecisionsTable({
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
            <th>Confidence</th>
            <th>Request</th>
            <th>Risk</th>
            <th>Execution</th>
            <th>Order</th>
            <th>LLM</th>
            <th>Latency</th>
            <th>Violations</th>
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
              <td>{formatPercent(row.confidence)}</td>
              <td>
                {row.requested_usdt_amount
                  ? `$${formatNumber(row.requested_usdt_amount, 2)}`
                  : row.requested_quantity
                    ? formatNumber(row.requested_quantity, 8)
                    : '-'}
              </td>
              <td>
                <span className={`badge ${statusClass(row.risk_status)}`}>{row.risk_status}</span>
              </td>
              <td>{row.execution_status}</td>
              <td>{row.exchange_order_id ?? '-'}</td>
              <td>{row.llm.model ?? '-'}</td>
              <td>{row.llm.latency_seconds ? `${formatNumber(row.llm.latency_seconds, 2)}s` : '-'}</td>
              <td className="truncate">{row.risk_violations.length ? firstJsonValue(row.risk_violations[0]) : '-'}</td>
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

export function PredictionsTable({ rows }: { rows: PredictionRow[] }) {
  if (!rows.length) return <EmptyState message="No predictions found." />
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Model</th>
            <th>Kind</th>
            <th>Horizon</th>
            <th>Target</th>
            <th>Direction</th>
            <th>Ref</th>
            <th>Pred</th>
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
              <td>{row.artifact_kind}</td>
              <td>{row.forecast_horizon}</td>
              <td>{row.target_mode}</td>
              <td>
                <span className={`badge ${statusClass(row.predicted_direction)}`}>{row.predicted_direction}</span>
              </td>
              <td>{formatNumber(row.reference_value, 2)}</td>
              <td>{formatNumber(row.predicted_value, 2)}</td>
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
