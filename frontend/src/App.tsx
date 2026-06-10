import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  Database,
  RefreshCw,
  Shield,
  ShoppingCart,
  Wallet,
} from 'lucide-react'

import './App.css'
import type { ModelArtifact } from './api'
import { getDashboardSummary, getHealth, getModelArtifacts, getSpotDemoPortfolio, getSymbols, submitSpotDemoMarketBuy, submitSpotDemoMarketSell } from './api'
import { AgentActionControls } from './dashboard/agent-controls'
import { DatabaseMarketControls } from './dashboard/data-controls'
import { INTERVALS, formatAge, formatNumber, formatPercent, formatTime } from './dashboard/format'
import { LiveLoopPanel } from './dashboard/live-loop-panel'
import { LiveCyclePanel } from './dashboard/live-cycle-panel'
import { ModelRegistryPanel } from './dashboard/model-registry'
import { PredictionControls } from './dashboard/prediction-controls'
import { Metric, MutationResult, Panel } from './dashboard/primitives'
import { RiskControlsPanel } from './dashboard/risk-controls'
import { RISK_PRESETS, type RiskPreset, type RiskSettings } from './dashboard/risk-settings'
import { IndicatorsPanel, PromptDrawer, RiskList, SystemHealthPanel } from './dashboard/summary'
import { DecisionsTable, PredictionsTable } from './dashboard/tables'
import { TrainingPanel } from './dashboard/training-panel'

function ManualSpotDemoPanel({
  symbol,
  onCompleted,
}: {
  symbol: string
  onCompleted: () => void
}) {
  const [buyAmount, setBuyAmount] = useState(10)
  const [sellQuantity, setSellQuantity] = useState(0.0001)
  const [confirmBuy, setConfirmBuy] = useState(false)
  const [confirmSell, setConfirmSell] = useState(false)

  const buyMutation = useMutation({
    mutationFn: () => submitSpotDemoMarketBuy({ symbol, usdt_amount: buyAmount, confirm: confirmBuy }),
    onSuccess: onCompleted,
  })
  const sellMutation = useMutation({
    mutationFn: () => submitSpotDemoMarketSell({ symbol, quantity: sellQuantity, confirm: confirmSell }),
    onSuccess: onCompleted,
  })

  return (
    <Panel title="Manual Spot Demo Orders" icon={<ShoppingCart size={17} />}>
      <div className="control-grid">
        <form
          className="control-form"
          onSubmit={(event) => {
            event.preventDefault()
            buyMutation.mutate()
          }}
        >
          <h3>Market Buy</h3>
          <label>
            USDT Amount
            <input type="number" min="0.01" step="0.01" value={buyAmount} onChange={(event) => setBuyAmount(Number(event.target.value))} />
          </label>
          <label className="check-row">
            <input type="checkbox" checked={confirmBuy} onChange={(event) => setConfirmBuy(event.target.checked)} />
            Confirm buy
          </label>
          <button type="submit" disabled={!confirmBuy || buyMutation.isPending}>
            Buy
          </button>
        </form>

        <form
          className="control-form"
          onSubmit={(event) => {
            event.preventDefault()
            sellMutation.mutate()
          }}
        >
          <h3>Market Sell</h3>
          <label>
            Quantity
            <input type="number" min="0.00000001" step="0.00000001" value={sellQuantity} onChange={(event) => setSellQuantity(Number(event.target.value))} />
          </label>
          <label className="check-row">
            <input type="checkbox" checked={confirmSell} onChange={(event) => setConfirmSell(event.target.checked)} />
            Confirm sell
          </label>
          <button type="submit" disabled={!confirmSell || sellMutation.isPending}>
            Sell
          </button>
        </form>
      </div>
      <MutationResult title="Buy Result" data={buyMutation.data} error={buyMutation.error} />
      <MutationResult title="Sell Result" data={sellMutation.data} error={sellMutation.error} />
    </Panel>
  )
}

function App() {
  const queryClient = useQueryClient()
  const [interval, setInterval] = useState('1m')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [limit, setLimit] = useState(20)
  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(null)
  const [liveMode, setLiveMode] = useState<'dry-run' | 'spot-demo'>('dry-run')
  const [marketDataMode, setMarketDataMode] = useState<'demo' | 'live'>('demo')
  const [selectedModelArtifacts, setSelectedModelArtifacts] = useState<{ key: string; paths: string[] } | null>(null)
  const [allowLargeGapRecovery, setAllowLargeGapRecovery] = useState(false)
  const [allowStaleModels, setAllowStaleModels] = useState(false)
  const [riskPreset, setRiskPreset] = useState<RiskPreset>('normal')
  const [riskSettings, setRiskSettings] = useState<RiskSettings>(RISK_PRESETS.normal)

  const healthQuery = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 30_000 })
  const symbolsQuery = useQuery({ queryKey: ['symbols', interval], queryFn: () => getSymbols(interval) })
  const portfolioQuery = useQuery({
    queryKey: ['spot-demo-portfolio', symbol],
    queryFn: () => getSpotDemoPortfolio(symbol),
    refetchInterval: 30_000,
  })
  const summaryQuery = useQuery({
    queryKey: ['summary', symbol, interval, limit],
    queryFn: () => getDashboardSummary({ symbol, interval, limit, lookbackHours: 24 }),
    refetchInterval: 30_000,
  })
  const modelArtifactsQuery = useQuery({
    queryKey: ['model-artifacts', symbol, interval],
    queryFn: () => getModelArtifacts({ symbol, interval }),
    refetchInterval: 60_000,
  })

  const refreshOperationalData = () => {
    queryClient.invalidateQueries({ queryKey: ['summary'] })
    queryClient.invalidateQueries({ queryKey: ['spot-demo-portfolio'] })
    queryClient.invalidateQueries({ queryKey: ['model-artifacts'] })
  }
  const applyRiskPreset = (preset: RiskPreset) => {
    setRiskPreset(preset)
    setRiskSettings(RISK_PRESETS[preset])
  }

  const modelArtifactsResponse = modelArtifactsQuery.data
  const allModelArtifacts = useMemo(() => modelArtifactsResponse?.artifacts ?? [], [modelArtifactsResponse])
  const selectableModelArtifacts = useMemo(
    () => allModelArtifacts.filter((artifact) => artifact.active && !artifact.archived),
    [allModelArtifacts],
  )
  const selectableArtifactPaths = useMemo(
    () => new Set(selectableModelArtifacts.map((artifact) => artifact.artifact_path)),
    [selectableModelArtifacts],
  )
  const latestModelArtifacts = useMemo(
    () => (modelArtifactsResponse?.latest_by_model ?? []).filter((artifact) => artifact.active && !artifact.archived),
    [modelArtifactsResponse],
  )
  const artifactSelectionKey = `${symbol}:${interval}`
  const effectiveSelectedModelArtifacts = selectedModelArtifacts?.key === artifactSelectionKey
    ? selectedModelArtifacts.paths.filter((path) => selectableArtifactPaths.has(path))
    : latestModelArtifacts.map((artifact) => artifact.artifact_path)

  const symbols = symbolsQuery.data?.symbols.length ? symbolsQuery.data.symbols : [symbol]
  const symbolStatusByName = useMemo(
    () => new Map((symbolsQuery.data?.symbol_statuses ?? []).map((item) => [item.symbol, item])),
    [symbolsQuery.data?.symbol_statuses],
  )
  const summary = summaryQuery.data
  const latestDecision = summary?.recent_decisions[0]
  const latestPrice = summary?.position.current_price ?? null
  const modelCount = useMemo(() => {
    if (!summary) return 0
    return new Set(summary.recent_predictions.map((row) => row.model_name)).size
  }, [summary])

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">CAPM</p>
          <h1>Trading Dashboard</h1>
        </div>
        <div className="toolbar">
          <label>
            Symbol
            <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
              {symbols.map((item) => (
                <option key={item} value={item}>
                  {`${item} / candle ${formatAge(symbolStatusByName.get(item)?.latest_candle_age_seconds)} / indicator ${formatAge(symbolStatusByName.get(item)?.latest_indicator_age_seconds)}`}
                </option>
              ))}
            </select>
          </label>
          <label>
            Interval
            <select value={interval} onChange={(event) => setInterval(event.target.value)}>
              {INTERVALS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Rows
            <input type="number" min="5" max="100" step="5" value={limit} onChange={(event) => setLimit(Number(event.target.value))} />
          </label>
          <button type="button" className="refresh-button" onClick={() => summaryQuery.refetch()}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </header>

      {summaryQuery.error ? (
        <div className="error-banner">
          <AlertTriangle size={18} />
          <span>{summaryQuery.error.message}</span>
        </div>
      ) : null}
      {summary && (
        (summary.market.latest_candle_age_seconds ?? 0) > 180 ||
        !summary.market.indicator_ready ||
        (summary.market.latest_indicator_age_seconds ?? 0) > 180
      ) ? (
        <div className="error-banner">
          <AlertTriangle size={18} />
          <span>
            {`Data freshness warning: candle age ${formatAge(summary.market.latest_candle_age_seconds)}, indicator age ${formatAge(summary.market.latest_indicator_age_seconds)}, indicator ready ${summary.market.indicator_ready ? 'yes' : 'no'}.`}
          </span>
        </div>
      ) : null}

      <section className="metrics-grid">
        <Metric
          label="Latest Price"
          value={latestPrice ? `$${formatNumber(latestPrice, 2)}` : '-'}
          subvalue={summary?.market.latest_candle_time ? `Candle ${formatTime(summary.market.latest_candle_time)}` : 'No candle'}
          icon={<BarChart3 size={17} />}
        />
        <Metric
          label="Agent Decision"
          value={latestDecision?.action ?? '-'}
          subvalue={latestDecision ? `${latestDecision.risk_status} / ${latestDecision.execution_status}` : 'No decision'}
          icon={<Activity size={17} />}
        />
        <Metric
          label="Prediction Accuracy"
          value={formatPercent(summary?.prediction_summary.direction_accuracy)}
          subvalue={`${summary?.prediction_summary.settled_count ?? 0} settled / ${summary?.prediction_summary.prediction_count ?? 0} total`}
          icon={<Database size={17} />}
        />
        <Metric
          label="Models"
          value={String(modelCount)}
          subvalue={`Generated ${formatTime(summary?.generated_at)}`}
          icon={<Clock size={17} />}
        />
        <Metric
          label="API Health"
          value={healthQuery.data?.status ?? '-'}
          subvalue={healthQuery.data ? `DB ${healthQuery.data.database} / LLM ${healthQuery.data.llm_provider?.status ?? '-'}` : 'Checking'}
          icon={<Database size={17} />}
        />
      </section>

      <SystemHealthPanel health={healthQuery.data} summary={summary} />
      <RiskControlsPanel
        preset={riskPreset}
        settings={riskSettings}
        onPresetChange={applyRiskPreset}
        onSettingsChange={setRiskSettings}
      />

      <div className="main-grid">
        <Panel title="Position And Risk" icon={<Shield size={17} />}>
          {summary ? <RiskList summary={summary} /> : <div className="empty">Loading risk state...</div>}
        </Panel>

        <Panel title="Market State" icon={<Wallet size={17} />}>
          {summary ? (
            <div className="kv-grid">
              <div>
                <span>Candle Time</span>
                <strong>{formatTime(summary.market.latest_candle_time)}</strong>
              </div>
              <div>
                <span>Candle Age</span>
                <strong>{formatAge(summary.market.latest_candle_age_seconds)}</strong>
              </div>
              <div>
                <span>Open</span>
                <strong>{summary.market.latest_candle ? `$${summary.market.latest_candle.open}` : '-'}</strong>
              </div>
              <div>
                <span>High</span>
                <strong>{summary.market.latest_candle ? `$${summary.market.latest_candle.high}` : '-'}</strong>
              </div>
              <div>
                <span>Low</span>
                <strong>{summary.market.latest_candle ? `$${summary.market.latest_candle.low}` : '-'}</strong>
              </div>
              <div>
                <span>Volume</span>
                <strong>{summary.market.latest_candle?.volume ?? '-'}</strong>
              </div>
            </div>
          ) : (
            <div className="empty">Loading market state...</div>
          )}
        </Panel>
      </div>

      <IndicatorsPanel summary={summary} />

      <div className="main-grid">
        <Panel title="Spot Demo Portfolio" icon={<Wallet size={17} />}>
          {portfolioQuery.data ? (
            <div className="kv-grid">
              <div>
                <span>USDT Free</span>
                <strong>{`$${formatNumber(portfolioQuery.data.portfolio.available_usdt, 2)}`}</strong>
              </div>
              <div>
                <span>Base Free</span>
                <strong>{formatNumber(portfolioQuery.data.portfolio.base_asset_free, 8)}</strong>
              </div>
              <div>
                <span>Base Locked</span>
                <strong>{formatNumber(portfolioQuery.data.portfolio.base_asset_locked, 8)}</strong>
              </div>
              <div>
                <span>Source</span>
                <strong>{portfolioQuery.data.symbol}</strong>
              </div>
            </div>
          ) : (
            <div className="empty">{portfolioQuery.error ? portfolioQuery.error.message : 'Loading portfolio...'}</div>
          )}
        </Panel>

        <ManualSpotDemoPanel symbol={symbol} onCompleted={refreshOperationalData} />
      </div>

      <LiveCyclePanel
        symbol={symbol}
        interval={interval}
        liveMode={liveMode}
        marketDataMode={marketDataMode}
        allowLargeGapRecovery={allowLargeGapRecovery}
        allowStaleModels={allowStaleModels}
        setLiveMode={setLiveMode}
        setMarketDataMode={setMarketDataMode}
        setAllowLargeGapRecovery={setAllowLargeGapRecovery}
        setAllowStaleModels={setAllowStaleModels}
        selectableModelArtifacts={selectableModelArtifacts as ModelArtifact[]}
        effectiveSelectedModelArtifacts={effectiveSelectedModelArtifacts}
        artifactSelectionKey={artifactSelectionKey}
        setSelectedModelArtifacts={setSelectedModelArtifacts}
        modelArtifactsQuery={{
          refetch: () => {
            void modelArtifactsQuery.refetch()
          },
          isFetching: modelArtifactsQuery.isFetching,
          error: modelArtifactsQuery.error,
        }}
        riskSettings={riskSettings}
        onCompleted={refreshOperationalData}
      />
      <LiveLoopPanel
        symbol={symbol}
        interval={interval}
        liveMode={liveMode}
        marketDataMode={marketDataMode}
        allowLargeGapRecovery={allowLargeGapRecovery}
        allowStaleModels={allowStaleModels}
        activeModelArtifacts={selectableModelArtifacts as ModelArtifact[]}
        riskSettings={riskSettings}
        onCompleted={refreshOperationalData}
      />

      <DatabaseMarketControls
        key={`data-controls:${symbol}:${interval}`}
        symbol={symbol}
        interval={interval}
        onCompleted={refreshOperationalData}
      />
      <TrainingPanel
        key={`training-panel:${symbol}:${interval}`}
        symbol={symbol}
        interval={interval}
        onCompleted={refreshOperationalData}
      />
      <ModelRegistryPanel
        artifacts={allModelArtifacts as ModelArtifact[]}
        isLoading={modelArtifactsQuery.isFetching}
        error={modelArtifactsQuery.error}
        onRefresh={() => {
          void modelArtifactsQuery.refetch()
        }}
      />
      <PredictionControls
        symbol={symbol}
        interval={interval}
        activeModelArtifacts={selectableModelArtifacts as ModelArtifact[]}
        modelArtifactsLoading={modelArtifactsQuery.isFetching}
        modelArtifactsError={modelArtifactsQuery.error}
        onRefreshModels={() => {
          void modelArtifactsQuery.refetch()
        }}
        onCompleted={refreshOperationalData}
      />
      <AgentActionControls symbol={symbol} interval={interval} riskSettings={riskSettings} onCompleted={refreshOperationalData} />

      <Panel title="Recent Decisions" icon={<Activity size={17} />}>
        <DecisionsTable rows={summary?.recent_decisions ?? []} onOpenPrompt={setSelectedPromptId} />
      </Panel>

      <Panel title="Recent Predictions" icon={<BarChart3 size={17} />}>
        <PredictionsTable rows={summary?.recent_predictions ?? []} />
      </Panel>

      {selectedPromptId !== null ? <PromptDrawer journalId={selectedPromptId} onClose={() => setSelectedPromptId(null)} /> : null}
    </main>
  )
}

export default App
