import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Database } from 'lucide-react'
import { useState } from 'react'

import type { BackfillIndicatorsRequest, FetchOhlcvRequest, IngestOhlcvRequest, RepairOhlcvGapsRequest } from '../api'
import { backfillIndicators, fetchOhlcv, getDataCoverage, ingestOhlcv, initDatabase, repairOhlcvGaps } from '../api'
import { defaultEnd, defaultStart } from './format'
import { CoverageResult, MutationResult, Panel } from './primitives'

export function DatabaseMarketControls({
  symbol,
  interval,
  onCompleted,
}: {
  symbol: string
  interval: string
  onCompleted: () => void
}) {
  const queryClient = useQueryClient()
  const [symbolsText, setSymbolsText] = useState(symbol)
  const [marketSymbol, setMarketSymbol] = useState(symbol)
  const [marketInterval, setMarketInterval] = useState(interval)
  const [start, setStart] = useState(defaultStart())
  const [end, setEnd] = useState(defaultEnd())
  const [marketMode, setMarketMode] = useState<'demo' | 'live'>('demo')
  const [persistFetch, setPersistFetch] = useState(false)
  const [ingestSource, setIngestSource] = useState<'rest' | 'dump' | 'dump-with-rest-tail'>('dump-with-rest-tail')
  const [batchSize, setBatchSize] = useState(50000)
  const [indicatorChunkSize, setIndicatorChunkSize] = useState(10000)
  const [resumeIndicators, setResumeIndicators] = useState(true)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['summary'] })
    queryClient.invalidateQueries({ queryKey: ['model-artifacts'] })
    onCompleted()
  }

  const initMutation = useMutation({
    mutationFn: () => initDatabase({ symbols: symbolsText.split(',').map((item) => item.trim()).filter(Boolean) }),
    onSuccess: invalidate,
  })
  const fetchMutation = useMutation({
    mutationFn: () => {
      const payload: FetchOhlcvRequest = {
        symbol: marketSymbol,
        interval: marketInterval,
        start,
        end,
        mode: marketMode,
        persist: persistFetch,
        batch_size: batchSize,
      }
      return fetchOhlcv(payload)
    },
    onSuccess: invalidate,
  })
  const ingestMutation = useMutation({
    mutationFn: () => {
      const payload: IngestOhlcvRequest = {
        symbol: marketSymbol,
        interval: marketInterval,
        start,
        end,
        source: ingestSource,
        mode: marketMode,
        batch_size: batchSize,
      }
      return ingestOhlcv(payload)
    },
    onSuccess: invalidate,
  })
  const coverageMutation = useMutation({
    mutationFn: () => getDataCoverage({ symbol: marketSymbol, interval: marketInterval, start, end }),
  })
  const repairMutation = useMutation({
    mutationFn: () => {
      const payload: RepairOhlcvGapsRequest = {
        symbol: marketSymbol,
        interval: marketInterval,
        start,
        end,
        mode: marketMode,
        batch_size: batchSize,
      }
      return repairOhlcvGaps(payload)
    },
    onSuccess: invalidate,
  })
  const indicatorBackfillMutation = useMutation({
    mutationFn: () => {
      const payload: BackfillIndicatorsRequest = {
        symbol: marketSymbol,
        interval: marketInterval,
        start,
        end,
        chunk_candle_count: indicatorChunkSize,
        resume_from_latest: resumeIndicators,
      }
      return backfillIndicators(payload)
    },
    onSuccess: invalidate,
  })

  return (
    <Panel title="Database And Market Data" icon={<Database size={17} />}>
      <div className="control-grid three">
        <form className="control-form" onSubmit={(event) => { event.preventDefault(); initMutation.mutate() }}>
          <h3>Init DB</h3>
          <label>
            Symbols
            <input value={symbolsText} onChange={(event) => setSymbolsText(event.target.value)} />
          </label>
          <button type="submit" disabled={initMutation.isPending}>Initialize</button>
        </form>

        <form className="control-form wide" onSubmit={(event) => { event.preventDefault(); fetchMutation.mutate() }}>
          <h3>Fetch OHLCV</h3>
          <div className="form-grid">
            <label>Symbol<input value={marketSymbol} onChange={(event) => setMarketSymbol(event.target.value)} /></label>
            <label>Interval<input value={marketInterval} onChange={(event) => setMarketInterval(event.target.value)} /></label>
            <label>Mode<select value={marketMode} onChange={(event) => setMarketMode(event.target.value as 'demo' | 'live')}><option value="demo">demo</option><option value="live">live</option></select></label>
            <label>Batch<input type="number" min="1" value={batchSize} onChange={(event) => setBatchSize(Number(event.target.value))} /></label>
            <label>Start<input value={start} onChange={(event) => setStart(event.target.value)} /></label>
            <label>End<input value={end} onChange={(event) => setEnd(event.target.value)} /></label>
            <label className="check-row"><input type="checkbox" checked={persistFetch} onChange={(event) => setPersistFetch(event.target.checked)} />Persist fetched candles</label>
          </div>
          <button type="submit" disabled={fetchMutation.isPending}>Fetch</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); ingestMutation.mutate() }}>
          <h3>Ingest OHLCV</h3>
          <label>
            Source
            <select value={ingestSource} onChange={(event) => setIngestSource(event.target.value as 'rest' | 'dump' | 'dump-with-rest-tail')}>
              <option value="dump-with-rest-tail">dump-with-rest-tail</option>
              <option value="dump">dump</option>
              <option value="rest">rest</option>
            </select>
          </label>
          <button type="submit" disabled={ingestMutation.isPending}>Ingest</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); coverageMutation.mutate() }}>
          <h3>Coverage</h3>
          <button type="submit" disabled={coverageMutation.isPending}>Inspect Coverage</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); repairMutation.mutate() }}>
          <h3>Repair Gaps</h3>
          <button type="submit" disabled={repairMutation.isPending}>Repair Missing OHLCV</button>
        </form>

        <form className="control-form" onSubmit={(event) => { event.preventDefault(); indicatorBackfillMutation.mutate() }}>
          <h3>Backfill Indicators</h3>
          <label>Chunk Size<input type="number" min="1" value={indicatorChunkSize} onChange={(event) => setIndicatorChunkSize(Number(event.target.value))} /></label>
          <label className="check-row"><input type="checkbox" checked={resumeIndicators} onChange={(event) => setResumeIndicators(event.target.checked)} />Resume from latest</label>
          <button type="submit" disabled={indicatorBackfillMutation.isPending}>Compute Indicators</button>
        </form>
      </div>
      <CoverageResult data={coverageMutation.data} />
      <MutationResult title="Init Result" data={initMutation.data} error={initMutation.error} />
      <MutationResult title="Fetch Result" data={fetchMutation.data} error={fetchMutation.error} />
      <MutationResult title="Ingest Result" data={ingestMutation.data} error={ingestMutation.error} />
      <MutationResult title="Coverage Error" error={coverageMutation.error} />
      <MutationResult title="Repair Result" data={repairMutation.data} error={repairMutation.error} />
      <MutationResult title="Indicator Backfill Result" data={indicatorBackfillMutation.data} error={indicatorBackfillMutation.error} />
    </Panel>
  )
}
