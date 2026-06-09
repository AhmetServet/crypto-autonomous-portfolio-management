import { useMutation } from '@tanstack/react-query'
import { Activity } from 'lucide-react'
import { useState } from 'react'

import type { AgentRunOnceRequest } from '../api'
import { runAgentOnce, summarizeAgentJournal } from '../api'
import { defaultEnd, defaultStart } from './format'
import { MutationResult, Panel } from './primitives'

export function AgentActionControls({
  symbol,
  interval,
  onCompleted,
}: {
  symbol: string
  interval: string
  onCompleted: () => void
}) {
  const [policy, setPolicy] = useState<'threshold' | 'llm'>('threshold')
  const [mode, setMode] = useState<'dry-run' | 'spot-demo'>('dry-run')
  const [showPrompt, setShowPrompt] = useState(false)
  const [dryRunUsdt, setDryRunUsdt] = useState(1000)
  const [dryRunBase, setDryRunBase] = useState(0)
  const [minReturn, setMinReturn] = useState(0.0005)
  const [agentSummaryStart, setAgentSummaryStart] = useState(defaultStart())
  const [agentSummaryEnd, setAgentSummaryEnd] = useState(defaultEnd())

  const runMutation = useMutation({
    mutationFn: () => {
      const payload: AgentRunOnceRequest = {
        symbol: policy === 'threshold' ? symbol : null,
        interval,
        mode,
        policy,
        show_prompt: showPrompt,
        dry_run_usdt_balance: dryRunUsdt,
        dry_run_base_asset_balance: dryRunBase,
        max_trade_usdt: 25,
        max_position_usdt: 100,
        min_predicted_return: minReturn,
        prediction_staleness_minutes: 5,
        emergency_stop: false,
        max_daily_realized_loss_usdt: 50,
        max_orders_per_day: 20,
        order_cooldown_minutes: 5,
        max_total_exposure_usdt: 100,
      }
      return runAgentOnce(payload)
    },
    onSuccess: onCompleted,
  })
  const summaryMutation = useMutation({
    mutationFn: () => summarizeAgentJournal({ symbol, interval, start: agentSummaryStart, end: agentSummaryEnd }),
  })

  return (
    <Panel title="Agent Actions" icon={<Activity size={17} />}>
      <div className="control-grid">
        <form className="control-form" onSubmit={(event) => { event.preventDefault(); runMutation.mutate() }}>
          <h3>Run Agent Once</h3>
          <div className="form-grid">
            <label>Policy<select value={policy} onChange={(event) => setPolicy(event.target.value as 'threshold' | 'llm')}><option value="threshold">threshold</option><option value="llm">llm</option></select></label>
            <label>Mode<select value={mode} onChange={(event) => setMode(event.target.value as 'dry-run' | 'spot-demo')}><option value="dry-run">dry-run</option><option value="spot-demo">spot-demo</option></select></label>
            <label>Dry USDT<input type="number" min="0" value={dryRunUsdt} onChange={(event) => setDryRunUsdt(Number(event.target.value))} /></label>
            <label>Dry Base<input type="number" min="0" value={dryRunBase} onChange={(event) => setDryRunBase(Number(event.target.value))} /></label>
            <label>Min Return<input type="number" step="0.0001" value={minReturn} onChange={(event) => setMinReturn(Number(event.target.value))} /></label>
            <label className="check-row"><input type="checkbox" checked={showPrompt} onChange={(event) => setShowPrompt(event.target.checked)} />Show LLM prompt</label>
          </div>
          <button type="submit" disabled={runMutation.isPending}>Run Agent</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); summaryMutation.mutate() }}>
          <h3>Agent Summary</h3>
          <label>Start<input value={agentSummaryStart} onChange={(event) => setAgentSummaryStart(event.target.value)} /></label>
          <label>End<input value={agentSummaryEnd} onChange={(event) => setAgentSummaryEnd(event.target.value)} /></label>
          <button type="submit" disabled={summaryMutation.isPending}>Summarize Agent</button>
        </form>
      </div>
      <MutationResult title="Agent Result" data={runMutation.data} error={runMutation.error} />
      <MutationResult title="Agent Summary Result" data={summaryMutation.data} error={summaryMutation.error} />
    </Panel>
  )
}
