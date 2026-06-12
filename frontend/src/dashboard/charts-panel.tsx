import { useMemo, useState, type ReactNode } from 'react'
import { Activity, BarChart3, TrendingUp } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { getDashboardCharts } from '../api'
import type { DashboardChartsResponse } from '../api'
import { compactTime, formatNumber } from './format'
import { EmptyState, Panel } from './primitives'

type ChartPoint = Record<string, string | number | null>

const INDICATOR_KEYS = [
  'sma_20_close',
  'ema_20_close',
  'bbands_20_2_lower',
  'bbands_20_2_middle',
  'bbands_20_2_upper',
  'rsi_14_close',
  'macd_12_26_9_line',
  'macd_12_26_9_signal',
  'macd_12_26_9_histogram',
]

export function DashboardChartsPanel({
  symbol,
  interval,
}: {
  symbol: string
  interval: string
}) {
  const [lookbackHours, setLookbackHours] = useState(24)
  const chartsQuery = useQuery({
    queryKey: ['dashboard-charts', symbol, interval, lookbackHours],
    queryFn: () => getDashboardCharts({ symbol, interval, lookbackHours, limit: 720 }),
    refetchInterval: 30_000,
  })

  const chartData = useMemo(() => buildChartData(chartsQuery.data), [chartsQuery.data])
  const activeIndicators = useMemo(() => {
    const keys = new Set<string>()
    chartData.forEach((point) => {
      INDICATOR_KEYS.forEach((key) => {
        if (typeof point[key] === 'number') keys.add(key)
      })
    })
    return Array.from(keys)
  }, [chartData])
  const pnlData = useMemo(
    () => (chartsQuery.data?.pnl_curve ?? []).map((row) => ({
      time: compactTime(row.time),
      cumulative_realized_pnl_usdt: row.cumulative_realized_pnl_usdt,
      realized_pnl_usdt: row.realized_pnl_usdt,
      side: row.side,
    })),
    [chartsQuery.data],
  )

  return (
    <Panel
      title="Dashboard Charts"
      icon={<BarChart3 size={17} />}
      action={
        <label className="inline-control">
          Lookback
          <select value={lookbackHours} onChange={(event) => setLookbackHours(Number(event.target.value))}>
            <option value={1}>1h</option>
            <option value={6}>6h</option>
            <option value={24}>24h</option>
            <option value={72}>72h</option>
            <option value={168}>7d</option>
          </select>
        </label>
      }
    >
      {chartsQuery.error ? <div className="empty">{chartsQuery.error.message}</div> : null}
      {!chartData.length ? (
        <EmptyState message={chartsQuery.isLoading ? 'Loading chart data...' : 'No chart data found.'} />
      ) : (
        <div className="charts-grid">
          <ChartFrame title="Price / Predictions / Decisions" icon={<TrendingUp size={16} />}>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 12, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#1f3446" vertical={false} />
                <XAxis dataKey="time" minTickGap={38} tick={{ fontSize: 11, fill: '#9fb0bf' }} />
                <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: '#9fb0bf' }} width={70} />
                <Tooltip content={<ChartTooltip />} />
                <Legend />
                <Line type="monotone" dataKey="close" stroke="#f4c744" strokeWidth={2} dot={false} />
                {activeIndicators.filter((key) => !key.startsWith('rsi_') && !key.startsWith('macd_')).map((key, index) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={indicatorStroke(index)}
                    strokeDasharray={index % 2 ? '4 3' : undefined}
                    strokeWidth={1}
                    dot={false}
                    connectNulls
                  />
                ))}
                <Scatter name="prediction up" dataKey="prediction_up" fill="#00d084" shape="triangle" />
                <Scatter name="prediction down" dataKey="prediction_down" fill="#ff4d4f" shape="diamond" />
                <Scatter name="buy" dataKey="buy_marker" fill="#26a69a" shape="triangle" />
                <Scatter name="sell" dataKey="sell_marker" fill="#ef5350" shape="diamond" />
                <Scatter name="hold" dataKey="hold_marker" fill="#8ea2b3" shape="circle" />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>

          <ChartFrame title="Indicator Detail" icon={<Activity size={16} />}>
            <ResponsiveContainer width="100%" height={185}>
              <ComposedChart data={chartData} margin={{ top: 12, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#1f3446" vertical={false} />
                <XAxis dataKey="time" minTickGap={38} tick={{ fontSize: 11, fill: '#9fb0bf' }} />
                <YAxis tick={{ fontSize: 11, fill: '#9fb0bf' }} width={70} />
                <Tooltip content={<ChartTooltip />} />
                <Legend />
                <ReferenceLine y={50} stroke="#536a7e" strokeDasharray="3 3" />
                {activeIndicators.filter((key) => key.startsWith('rsi_') || key.startsWith('macd_')).map((key, index) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={indicatorStroke(index)}
                    strokeWidth={1}
                    dot={false}
                    connectNulls
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>

          <ChartFrame title="Realized PnL Curve" icon={<Activity size={16} />}>
            {pnlData.length ? (
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={pnlData} margin={{ top: 12, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#1f3446" vertical={false} />
                  <XAxis dataKey="time" minTickGap={38} tick={{ fontSize: 11, fill: '#9fb0bf' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#9fb0bf' }} width={70} />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend />
                  <ReferenceLine y={0} stroke="#536a7e" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="cumulative_realized_pnl_usdt" stroke="#00d084" strokeWidth={2} dot />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState message="No filled sell orders with realized PnL found." />
            )}
          </ChartFrame>
        </div>
      )}
    </Panel>
  )
}

function ChartFrame({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <div className="chart-frame">
      <h3>{icon}{title}</h3>
      {children}
    </div>
  )
}

function buildChartData(payload?: DashboardChartsResponse): ChartPoint[] {
  if (!payload) return []
  const byTime = new Map<string, ChartPoint>()
  payload.candles.forEach((row) => {
    const time = compactTime(row.time)
    byTime.set(row.time, {
      source_time: row.time,
      time,
      close: row.close,
      open: row.open,
      high: row.high,
      low: row.low,
      ...row.indicators,
    })
  })
  payload.prediction_markers.forEach((row) => {
    const point = byTime.get(row.reference_time)
    if (!point) return
    point[row.predicted_direction === 'down' ? 'prediction_down' : 'prediction_up'] = row.reference_value
  })
  payload.decision_markers.forEach((row) => {
    const point = byTime.get(row.reference_time)
    if (!point || typeof point.close !== 'number') return
    point[`${row.action}_marker`] = point.close
  })
  return Array.from(byTime.values())
}

function indicatorStroke(index: number) {
  return ['#4fc3f7', '#ab47bc', '#ff9800', '#7e57c2', '#26a69a'][index % 5]
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: unknown }>; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((item) => (
        <span key={item.name}>{`${item.name}: ${typeof item.value === 'number' ? formatNumber(item.value, 4) : item.value}`}</span>
      ))}
    </div>
  )
}
