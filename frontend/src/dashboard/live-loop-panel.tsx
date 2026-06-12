import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, Play, RefreshCw, Square } from 'lucide-react'
import { useState } from 'react'

import type { LiveLoop, LiveLoopRequest, ModelArtifact } from '../api'
import { getLiveLoop, getLiveLoops, startLiveLoop, stopLiveLoop } from '../api'
import { compactTime } from './format'
import { EmptyState, MutationResult, Panel } from './primitives'
import type { RiskSettings } from './risk-settings'

function loopIsActive(loop: LiveLoop) {
  return loop.status === 'queued' || loop.status === 'running' || loop.status === 'stop_requested'
}

export function LiveLoopPanel({
  symbol,
  interval,
  liveMode,
  marketDataMode,
  allowLargeGapRecovery,
  allowStaleModels,
  activeModelArtifacts,
  riskSettings,
  onCompleted,
}: {
  symbol: string
  interval: string
  liveMode: 'dry-run' | 'spot-demo'
  marketDataMode: 'demo' | 'live'
  allowLargeGapRecovery: boolean
  allowStaleModels: boolean
  activeModelArtifacts: ModelArtifact[]
  riskSettings: RiskSettings
  onCompleted: () => void
}) {
  const queryClient = useQueryClient()
  const [runIndefinitely, setRunIndefinitely] = useState(false)
  const [maxCycles, setMaxCycles] = useState(10)
  const [cycleOffsetSeconds, setCycleOffsetSeconds] = useState(2)
  const [stopAfterErrorCount, setStopAfterErrorCount] = useState(3)
  const [sleepAfterErrorSeconds, setSleepAfterErrorSeconds] = useState(10)
  const [selectedLoopId, setSelectedLoopId] = useState<string | null>(null)

  const loopsQuery = useQuery({ queryKey: ['live-loops'], queryFn: getLiveLoops, refetchInterval: 3_000 })
  const selectedLoopQuery = useQuery({
    queryKey: ['live-loop', selectedLoopId],
    queryFn: () => getLiveLoop(String(selectedLoopId)),
    enabled: selectedLoopId !== null,
    refetchInterval: selectedLoopId ? 2_000 : false,
  })
  const startMutation = useMutation({
    mutationFn: () => {
      const request: LiveLoopRequest = {
        interval,
        mode: liveMode,
        market_data_mode: marketDataMode,
        model_artifacts: activeModelArtifacts.map((artifact) => `${symbol}=${artifact.artifact_path}`),
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
        cycle_offset_seconds: cycleOffsetSeconds,
        max_cycles: runIndefinitely ? null : maxCycles,
        stop_after_error_count: stopAfterErrorCount,
        sleep_after_error_seconds: sleepAfterErrorSeconds,
        name: `${symbol}-${interval}-${liveMode}`,
      }
      return startLiveLoop(request)
    },
    onSuccess: (data) => {
      setSelectedLoopId(data.loop.id)
      queryClient.invalidateQueries({ queryKey: ['live-loops'] })
      onCompleted()
    },
  })
  const stopMutation = useMutation({
    mutationFn: (loopId: string) => stopLiveLoop(loopId),
    onSuccess: (data) => {
      setSelectedLoopId(data.loop.id)
      queryClient.invalidateQueries({ queryKey: ['live-loops'] })
      queryClient.invalidateQueries({ queryKey: ['live-loop'] })
      onCompleted()
    },
  })

  const loops = loopsQuery.data?.loops ?? []
  const activeLoop = loops.find(loopIsActive)
  const selectedLoop = selectedLoopQuery.data?.loop ?? loops.find((loop) => loop.id === selectedLoopId)
  const latestLoop = loops[0]

  return (
    <Panel
      title="Live Agent Loop"
      icon={<RefreshCw size={17} />}
      action={(
        <button type="button" className="refresh-button" onClick={() => loopsQuery.refetch()} disabled={loopsQuery.isFetching}>
          <RefreshCw size={15} />
          Refresh
        </button>
      )}
    >
      <div className="control-grid three">
        <form className="control-form" onSubmit={(event) => { event.preventDefault(); startMutation.mutate() }}>
          <h3>Start Loop</h3>
          <label className="check-row">
            <input type="checkbox" checked={runIndefinitely} onChange={(event) => setRunIndefinitely(event.target.checked)} />
            Run indefinitely
          </label>
          <label>Max Cycles<input type="number" min="1" disabled={runIndefinitely} value={maxCycles} onChange={(event) => setMaxCycles(Number(event.target.value))} /></label>
          <label>Cycle Offset Seconds<input type="number" min="0" step="0.5" value={cycleOffsetSeconds} onChange={(event) => setCycleOffsetSeconds(Number(event.target.value))} /></label>
          <label>Stop After Errors<input type="number" min="1" value={stopAfterErrorCount} onChange={(event) => setStopAfterErrorCount(Number(event.target.value))} /></label>
          <label>Sleep After Error Seconds<input type="number" min="0" step="1" value={sleepAfterErrorSeconds} onChange={(event) => setSleepAfterErrorSeconds(Number(event.target.value))} /></label>
          <button type="submit" disabled={startMutation.isPending || Boolean(activeLoop) || !activeModelArtifacts.length}>
            <Play size={15} />
            Start Loop
          </button>
        </form>

        <div className="control-form">
          <h3>Current Status</h3>
          <div className="kv-mini">
            <span>Active</span><strong>{activeLoop ? activeLoop.status : 'none'}</strong>
            <span>Last Loop</span><strong>{latestLoop ? `${latestLoop.status} / ${compactTime(latestLoop.created_at)}` : '-'}</strong>
            <span>Next Cycle</span><strong>{activeLoop ? `after candle close + ${activeLoop.cycle_offset_seconds}s` : '-'}</strong>
            <span>PID</span><strong>{activeLoop?.pid ?? '-'}</strong>
          </div>
          {activeLoop ? (
            <button type="button" disabled={stopMutation.isPending} onClick={() => stopMutation.mutate(activeLoop.id)}>
              <Square size={15} />
              Stop Loop
            </button>
          ) : null}
        </div>

        <div className="control-form">
          <h3>Runtime Inputs</h3>
          <div className="kv-mini">
            <span>Symbol</span><strong>{symbol}</strong>
            <span>Interval</span><strong>{interval}</strong>
            <span>Mode</span><strong>{liveMode}</strong>
            <span>Market</span><strong>{marketDataMode}</strong>
            <span>Gap Recovery</span><strong>{allowLargeGapRecovery ? 'allowed' : 'blocked'}</strong>
            <span>Stale Models</span><strong>{allowStaleModels ? 'allowed' : 'blocked'}</strong>
            <span>Models</span><strong>{activeModelArtifacts.length}</strong>
          </div>
        </div>
      </div>

      {loopsQuery.error ? <div className="inline-error">{loopsQuery.error.message}</div> : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Created</th>
              <th>Name</th>
              <th>Status</th>
              <th>Mode</th>
              <th>Max Cycles</th>
              <th>PID</th>
              <th>Return</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loops.map((loop) => (
              <tr key={loop.id}>
                <td>{compactTime(loop.created_at)}</td>
                <td>{loop.name}</td>
                <td><span className={`badge ${loop.status === 'running' ? 'good' : loop.status === 'failed' ? 'bad' : 'neutral'}`}>{loop.status}</span></td>
                <td>{loop.mode}</td>
                <td>{loop.max_cycles ?? 'infinite'}</td>
                <td>{loop.pid ?? '-'}</td>
                <td>{loop.return_code ?? '-'}</td>
                <td className="actions">
                  <button type="button" className="icon-button" title="View logs" onClick={() => setSelectedLoopId(loop.id)}>
                    <Eye size={15} />
                  </button>
                  {loopIsActive(loop) ? (
                    <button type="button" className="icon-button" title="Stop" onClick={() => stopMutation.mutate(loop.id)}>
                      <Square size={15} />
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!loops.length ? <EmptyState message={loopsQuery.isFetching ? 'Loading live loops...' : 'No dashboard live loops in this API process.'} /> : null}
      {selectedLoop ? (
        <div className="result-block">
          <h3>{`Loop Log / ${selectedLoop.name}`}</h3>
          <pre>{selectedLoop.log ?? 'Loading log...'}</pre>
        </div>
      ) : null}
      <MutationResult title="Start Loop Result" data={startMutation.data} error={startMutation.error} />
      <MutationResult title="Stop Loop Result" data={stopMutation.data} error={stopMutation.error} />
    </Panel>
  )
}
