import { useMutation } from '@tanstack/react-query'
import { BarChart3, Play } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { JournalSummaryRequest, ModelArtifact, PredictBatchRequest, PredictRequest, PredictionResult, SettlePredictionsRequest } from '../api'
import { runPrediction, runPredictionBatch, settlePredictions, summarizePredictionJournal } from '../api'
import { artifactLabel, defaultEnd, defaultStart, formatNumber, formatPercent, formatTime } from './format'
import { EmptyState, MutationResult, Panel } from './primitives'

function PredictionDetail({ prediction }: { prediction: PredictionResult }) {
  return (
    <div className="prediction-detail">
      <div className="kv-grid">
        <div><span>Model</span><strong>{prediction.model_name}</strong></div>
        <div><span>Reference</span><strong>{formatTime(prediction.reference_time)}</strong></div>
        <div><span>Prediction Time</span><strong>{formatTime(prediction.prediction_time)}</strong></div>
        <div><span>Predicted Return</span><strong>{formatPercent(prediction.predicted_return)}</strong></div>
        <div><span>Reference Value</span><strong>{formatNumber(prediction.reference_value, 4)}</strong></div>
        <div><span>Predicted Value</span><strong>{formatNumber(prediction.predicted_value, 4)}</strong></div>
        <div><span>Horizon</span><strong>{prediction.forecast_horizon}</strong></div>
        <div><span>Window Size</span><strong>{prediction.feature_window.window_size}</strong></div>
      </div>
      <div className="inline-note">
        {`Feature window: ${prediction.feature_window.reference_time} -> ${prediction.feature_window.prediction_time}. Features: ${prediction.feature_window.feature_names.length ? prediction.feature_window.feature_names.join(', ') : 'price-only model'}.`}
      </div>
    </div>
  )
}

export function PredictionControls({
  symbol,
  interval,
  activeModelArtifacts,
  modelArtifactsLoading,
  modelArtifactsError,
  onRefreshModels,
  onCompleted,
}: {
  symbol: string
  interval: string
  activeModelArtifacts: ModelArtifact[]
  modelArtifactsLoading: boolean
  modelArtifactsError: Error | null
  onRefreshModels: () => void
  onCompleted: () => void
}) {
  const [selectedArtifactPath, setSelectedArtifactPath] = useState('')
  const [referenceTime, setReferenceTime] = useState('')
  const [journalPrediction, setJournalPrediction] = useState(false)
  const [settleUntil, setSettleUntil] = useState('')
  const [settleLimit, setSettleLimit] = useState(1000)
  const [summaryStart, setSummaryStart] = useState(defaultStart())
  const [summaryEnd, setSummaryEnd] = useState(defaultEnd())
  const [modelName, setModelName] = useState('')
  const selectedArtifact = useMemo(
    () => activeModelArtifacts.find((artifact) => artifact.artifact_path === selectedArtifactPath) ?? activeModelArtifacts[0],
    [activeModelArtifacts, selectedArtifactPath],
  )

  const predictMutation = useMutation({
    mutationFn: () => {
      if (!selectedArtifact) throw new Error('No active model artifact selected.')
      const payload: PredictRequest = {
        symbol,
        interval,
        model_artifact: selectedArtifact.artifact_path,
        at: referenceTime.trim() || null,
        journal: journalPrediction,
      }
      return runPrediction(payload)
    },
    onSuccess: onCompleted,
  })
  const predictAllMutation = useMutation({
    mutationFn: () => {
      const payload: PredictBatchRequest = {
        symbol,
        interval,
        model_artifacts: activeModelArtifacts.map((artifact) => artifact.artifact_path),
        at: referenceTime.trim() || null,
        journal: journalPrediction,
      }
      return runPredictionBatch(payload)
    },
    onSuccess: onCompleted,
  })
  const settleMutation = useMutation({
    mutationFn: () => {
      const payload: SettlePredictionsRequest = {
        symbol,
        interval,
        until: settleUntil.trim() || null,
        limit: settleLimit,
      }
      return settlePredictions(payload)
    },
    onSuccess: onCompleted,
  })
  const summaryMutation = useMutation({
    mutationFn: () => {
      const payload: JournalSummaryRequest = {
        symbol,
        interval,
        start: summaryStart,
        end: summaryEnd,
        model_name: modelName.trim() || null,
      }
      return summarizePredictionJournal(payload)
    },
  })

  return (
    <Panel title="Prediction Tools" icon={<BarChart3 size={17} />}>
      <div className="control-grid three">
        <form className="control-form wide" onSubmit={(event) => { event.preventDefault(); predictMutation.mutate() }}>
          <h3>Run Prediction</h3>
          <label>
            Active Model
            <select value={selectedArtifact?.artifact_path ?? ''} onChange={(event) => setSelectedArtifactPath(event.target.value)}>
              {activeModelArtifacts.map((artifact) => (
                <option key={artifact.artifact_path} value={artifact.artifact_path}>{artifactLabel(artifact)}</option>
              ))}
            </select>
          </label>
          <label>Reference Time<input placeholder="optional ISO timestamp" value={referenceTime} onChange={(event) => setReferenceTime(event.target.value)} /></label>
          <label className="check-row"><input type="checkbox" checked={journalPrediction} onChange={(event) => setJournalPrediction(event.target.checked)} />Journal prediction</label>
          {modelArtifactsError ? <div className="inline-error">{modelArtifactsError.message}</div> : null}
          {!activeModelArtifacts.length ? (
            <EmptyState message={modelArtifactsLoading ? 'Loading active model artifacts...' : 'No active model artifacts found for this symbol and interval.'} />
          ) : null}
          <div className="button-row">
            <button type="submit" disabled={!selectedArtifact || predictMutation.isPending}>
              <Play size={15} />
              Predict Selected
            </button>
            <button type="button" disabled={!activeModelArtifacts.length || predictAllMutation.isPending} onClick={() => predictAllMutation.mutate()}>
              <Play size={15} />
              Predict All Active
            </button>
            <button type="button" onClick={onRefreshModels} disabled={modelArtifactsLoading}>Refresh Models</button>
          </div>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); settleMutation.mutate() }}>
          <h3>Settle Predictions</h3>
          <label>Until<input placeholder="optional ISO timestamp" value={settleUntil} onChange={(event) => setSettleUntil(event.target.value)} /></label>
          <label>Limit<input type="number" min="1" value={settleLimit} onChange={(event) => setSettleLimit(Number(event.target.value))} /></label>
          <button type="submit" disabled={settleMutation.isPending}>Settle</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); summaryMutation.mutate() }}>
          <h3>Prediction Summary</h3>
          <label>Start<input value={summaryStart} onChange={(event) => setSummaryStart(event.target.value)} /></label>
          <label>End<input value={summaryEnd} onChange={(event) => setSummaryEnd(event.target.value)} /></label>
          <label>Model Name<input placeholder="optional" value={modelName} onChange={(event) => setModelName(event.target.value)} /></label>
          <button type="submit" disabled={summaryMutation.isPending}>Summarize</button>
        </form>
      </div>
      <MutationResult title="Prediction Result" data={predictMutation.data} error={predictMutation.error} />
      {predictMutation.data?.prediction ? <PredictionDetail prediction={predictMutation.data.prediction} /> : null}
      <MutationResult title="All Active Prediction Result" data={predictAllMutation.data} error={predictAllMutation.error} />
      {predictAllMutation.data?.results?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Artifact</th>
                <th>Status</th>
                <th>Model</th>
                <th>Reference</th>
                <th>Prediction</th>
                <th>Return</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {predictAllMutation.data.results.map((result) => (
                <tr key={result.artifact_path}>
                  <td className="truncate">{result.artifact_path}</td>
                  <td><span className={`badge ${result.status === 'ok' ? 'good' : 'bad'}`}>{result.status}</span></td>
                  <td>{result.status === 'ok' ? result.prediction.model_name : '-'}</td>
                  <td>{result.status === 'ok' ? formatTime(result.prediction.reference_time) : '-'}</td>
                  <td>{result.status === 'ok' ? formatTime(result.prediction.prediction_time) : '-'}</td>
                  <td>{result.status === 'ok' ? formatPercent(result.prediction.predicted_return) : '-'}</td>
                  <td className="truncate">{result.status === 'error' ? `${result.error_type}: ${result.reason}` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <MutationResult title="Settlement Result" data={settleMutation.data} error={settleMutation.error} />
      <MutationResult title="Prediction Summary Result" data={summaryMutation.data} error={summaryMutation.error} />
    </Panel>
  )
}
