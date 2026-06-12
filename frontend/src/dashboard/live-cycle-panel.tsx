import type { Dispatch, SetStateAction } from 'react'

import { useMutation } from '@tanstack/react-query'
import { Play, RefreshCw } from 'lucide-react'

import type { LiveCycleRequest, ModelArtifact } from '../api'
import { runLiveCycleOnce } from '../api'
import { artifactLabel } from './format'
import { EmptyState, MutationResult, Panel } from './primitives'
import type { RiskSettings } from './risk-settings'

export function LiveCyclePanel({
  symbol,
  interval,
  liveMode,
  marketDataMode,
  allowLargeGapRecovery,
  allowStaleModels,
  selectableModelArtifacts,
  effectiveSelectedModelArtifacts,
  artifactSelectionKey,
  setSelectedModelArtifacts,
  modelArtifactsQuery,
  riskSettings,
  onCompleted,
}: {
  symbol: string
  interval: string
  liveMode: 'dry-run' | 'spot-demo'
  marketDataMode: 'demo' | 'live'
  allowLargeGapRecovery: boolean
  allowStaleModels: boolean
  selectableModelArtifacts: ModelArtifact[]
  effectiveSelectedModelArtifacts: string[]
  artifactSelectionKey: string
  setSelectedModelArtifacts: Dispatch<SetStateAction<{ key: string; paths: string[] } | null>>
  modelArtifactsQuery: { refetch: () => void; isFetching: boolean; error: Error | null }
  riskSettings: RiskSettings
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
        max_trade_usdt: riskSettings.maxTradeUsdt,
        max_position_usdt: riskSettings.maxPositionUsdt,
        emergency_stop: riskSettings.emergencyStop,
        max_daily_realized_loss_usdt: riskSettings.maxDailyLossUsdt,
        max_orders_per_day: riskSettings.maxOrdersPerDay,
        order_cooldown_minutes: riskSettings.cooldownMinutes,
        max_total_exposure_usdt: riskSettings.maxExposureUsdt,
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
        <div className="runtime-summary">
          <span>{`Mode: ${liveMode}`}</span>
          <span>{`Market: ${marketDataMode}`}</span>
          <span>{allowLargeGapRecovery ? 'Large gap recovery on' : 'Large gap recovery off'}</span>
          <span>{allowStaleModels ? 'Stale models allowed' : 'Fresh models required'}</span>
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
