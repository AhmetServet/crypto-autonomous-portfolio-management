import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, Play, RefreshCw, Square } from 'lucide-react'
import { useState } from 'react'

import type { ModelArtifact } from '../api'
import { updateModelArtifactState } from '../api'
import { compactTime, formatNumber, formatPercent, modelStatus, statusClass } from './format'
import { EmptyState, MutationResult, Panel } from './primitives'

function PowerGlyph({ active }: { active: boolean }) {
  return active ? <Square size={14} /> : <Play size={14} />
}

export function ModelRegistryPanel({
  artifacts,
  isLoading,
  error,
  onRefresh,
}: {
  artifacts: ModelArtifact[]
  isLoading: boolean
  error: Error | null
  onRefresh: () => void
}) {
  const queryClient = useQueryClient()
  const [modelTypeFilter, setModelTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const stateMutation = useMutation({
    mutationFn: updateModelArtifactState,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['model-artifacts'] })
    },
  })
  const filtered = artifacts.filter((artifact) => {
    const status = modelStatus(artifact)
    return (modelTypeFilter === 'all' || artifact.model_type === modelTypeFilter)
      && (statusFilter === 'all' || status === statusFilter)
  })

  return (
    <Panel
      title="Model Registry"
      icon={<Archive size={17} />}
      action={(
        <button type="button" className="refresh-button" onClick={onRefresh} disabled={isLoading}>
          <RefreshCw size={15} />
          Refresh
        </button>
      )}
    >
      <div className="registry-toolbar">
        <label>
          Type
          <select value={modelTypeFilter} onChange={(event) => setModelTypeFilter(event.target.value)}>
            <option value="all">all</option>
            <option value="tabular">tabular</option>
            <option value="deep_learning">deep_learning</option>
            <option value="statistical">statistical</option>
            <option value="unknown">unknown</option>
          </select>
        </label>
        <label>
          Status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">all</option>
            <option value="active">active</option>
            <option value="stale">stale</option>
            <option value="inactive">inactive</option>
            <option value="archived">archived</option>
          </select>
        </label>
      </div>
      {error ? <div className="inline-error">{error.message}</div> : null}
      {!filtered.length ? (
        <EmptyState message={isLoading ? 'Loading model registry...' : 'No model artifacts match the filters.'} />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Type</th>
                <th>Status</th>
                <th>Trained</th>
                <th>Accuracy</th>
                <th>RMSE</th>
                <th>MAPE</th>
                <th>Return</th>
                <th>Trades</th>
                <th>Path</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((artifact) => (
                <tr key={artifact.artifact_path}>
                  <td>{artifact.model_name}</td>
                  <td>{artifact.model_type}</td>
                  <td><span className={`badge ${statusClass(modelStatus(artifact) === 'active')}`}>{modelStatus(artifact)}</span></td>
                  <td>{compactTime(artifact.trained_through ?? artifact.modified_at)}</td>
                  <td>{formatPercent(artifact.direction_accuracy)}</td>
                  <td>{formatNumber(artifact.rmse, 3)}</td>
                  <td>{formatPercent(artifact.mape)}</td>
                  <td>{formatPercent(artifact.cumulative_return)}</td>
                  <td>{artifact.trade_count ?? '-'}</td>
                  <td className="truncate">{artifact.artifact_path}</td>
                  <td className="actions">
                    <button
                      type="button"
                      className="icon-button"
                      title={artifact.active ? 'Mark inactive' : 'Mark active'}
                      onClick={() => stateMutation.mutate({ artifact_path: artifact.artifact_path, active: !artifact.active })}
                    >
                      <PowerGlyph active={artifact.active} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      title={artifact.archived ? 'Unarchive' : 'Archive'}
                      onClick={() => stateMutation.mutate({ artifact_path: artifact.artifact_path, archived: !artifact.archived })}
                    >
                      <Archive size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <MutationResult title="Registry Update" data={stateMutation.data} error={stateMutation.error} />
    </Panel>
  )
}
