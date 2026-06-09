import { useMutation } from '@tanstack/react-query'
import { BarChart3 } from 'lucide-react'
import { useState } from 'react'

import type { JournalSummaryRequest, PredictRequest, SettlePredictionsRequest } from '../api'
import { runPrediction, settlePredictions, summarizePredictionJournal } from '../api'
import { defaultEnd, defaultStart } from './format'
import { MutationResult, Panel } from './primitives'

export function PredictionControls({
  symbol,
  interval,
  onCompleted,
}: {
  symbol: string
  interval: string
  onCompleted: () => void
}) {
  const [modelArtifact, setModelArtifact] = useState('experiments/results/<run_id>/model.pkl')
  const [referenceTime, setReferenceTime] = useState('')
  const [journalPrediction, setJournalPrediction] = useState(false)
  const [settleUntil, setSettleUntil] = useState('')
  const [settleLimit, setSettleLimit] = useState(1000)
  const [summaryStart, setSummaryStart] = useState(defaultStart())
  const [summaryEnd, setSummaryEnd] = useState(defaultEnd())
  const [modelName, setModelName] = useState('')

  const predictMutation = useMutation({
    mutationFn: () => {
      const payload: PredictRequest = {
        symbol,
        interval,
        model_artifact: modelArtifact,
        at: referenceTime.trim() || null,
        journal: journalPrediction,
      }
      return runPrediction(payload)
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
          <label>Model Artifact<input value={modelArtifact} onChange={(event) => setModelArtifact(event.target.value)} /></label>
          <label>Reference Time<input placeholder="optional ISO timestamp" value={referenceTime} onChange={(event) => setReferenceTime(event.target.value)} /></label>
          <label className="check-row"><input type="checkbox" checked={journalPrediction} onChange={(event) => setJournalPrediction(event.target.checked)} />Journal prediction</label>
          <button type="submit" disabled={predictMutation.isPending}>Predict</button>
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
      <MutationResult title="Settlement Result" data={settleMutation.data} error={settleMutation.error} />
      <MutationResult title="Prediction Summary Result" data={summaryMutation.data} error={summaryMutation.error} />
    </Panel>
  )
}
