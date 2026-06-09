import type { Dispatch, SetStateAction } from 'react'

import { useMutation } from '@tanstack/react-query'
import { Play, RefreshCw } from 'lucide-react'

import type { LiveCycleRequest, ModelArtifact } from '../api'
import { runLiveCycleOnce } from '../api'
import { artifactLabel } from './format'
import { EmptyState, MutationResult, Panel } from './primitives'

export function LiveCyclePanel({
  symbol,
  interval,
  liveMode,
  marketDataMode,
  allowLargeGapRecovery,
  allowStaleModels,
  setLiveMode,
  setMarketDataMode,
  setAllowLargeGapRecovery,
  setAllowStaleModels,
  selectableModelArtifacts,
  effectiveSelectedModelArtifacts,
  artifactSelectionKey,
  setSelectedModelArtifacts,
  modelArtifactsQuery,
  onCompleted,
}: {
  symbol: string
  interval: string
  liveMode: 'dry-run' | 'spot-demo'
  marketDataMode: 'demo' | 'live'
  allowLargeGapRecovery: boolean
  allowStaleModels: boolean
  setLiveMode: (value: 'dry-run' | 'spot-demo') => void
  setMarketDataMode: (value: 'demo' | 'live') => void
  setAllowLargeGapRecovery: (value: boolean) => void
  setAllowStaleModels: (value: boolean) => void
  selectableModelArtifacts: ModelArtifact[]
  effectiveSelectedModelArtifacts: string[]
  artifactSelectionKey: string
  setSelectedModelArtifacts: Dispatch<SetStateAction<{ key: string; paths: string[] } | null>>
  modelArtifactsQuery: { refetch: () => void; isFetching: boolean; error: Error | null }
  onCompleted: () => void
}) {
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
    onSuccess: onCompleted,
  })

  return (
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
          {!selectableModelArtifacts.length && !modelArtifactsQuery.error ? (
            <EmptyState message={modelArtifactsQuery.isFetching ? 'Loading trained models...' : 'No active model artifacts found for this symbol and interval.'} />
          ) : (
            <div className="artifact-list">
              {selectableModelArtifacts.map((artifact) => {
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
  )
}
