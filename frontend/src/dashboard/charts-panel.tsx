import { useMemo, useState, type ReactNode } from 'react'
import { Activity, BarChart3, TrendingUp } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
  type ChartData,
  type ChartDataset,
  type ChartOptions,
  type Plugin,
  type TooltipItem,
} from 'chart.js'
import { Line } from 'react-chartjs-2'

import { getDashboardCharts } from '../api'
import type { DashboardChartsResponse } from '../api'
import { compactTime, formatNumber } from './format'
import { EmptyState, Panel } from './primitives'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

type ChartPoint = Record<string, string | number | null>
type ChartDatasetExtra = ChartDataset<'line', Array<number | null>> & { markerKind?: 'decision' }

const PRICE_INDICATOR_KEYS = [
  'sma_20_close',
  'ema_20_close',
  'bbands_20_2_lower',
  'bbands_20_2_middle',
  'bbands_20_2_upper',
]
const DETAIL_INDICATOR_KEYS = ['rsi_14_close', 'macd_12_26_9_line', 'macd_12_26_9_signal', 'macd_12_26_9_histogram']

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
  const priceChart = useMemo(() => buildPriceChart(chartData), [chartData])
  const candlestickPlugin = useMemo(() => buildCandlestickPlugin(chartData), [chartData])
  const indicatorChart = useMemo(() => buildIndicatorChart(chartData), [chartData])
  const pnlChart = useMemo(() => buildPnlChart(chartsQuery.data), [chartsQuery.data])

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
          <ChartFrame title="Price / Decisions" icon={<TrendingUp size={16} />}>
            <div className="chart-canvas chart-canvas-main">
              <Line data={priceChart} options={priceChartOptions} plugins={[candlestickPlugin]} />
            </div>
          </ChartFrame>

          <ChartFrame title="Indicator Detail" icon={<Activity size={16} />}>
            {indicatorChart.datasets.length ? (
              <div className="chart-canvas chart-canvas-small">
                <Line data={indicatorChart} options={indicatorChartOptions} />
              </div>
            ) : (
              <EmptyState message="No RSI or MACD values found for this window." />
            )}
          </ChartFrame>

          <ChartFrame title="Realized PnL Curve" icon={<Activity size={16} />}>
            {pnlChart.datasets.length ? (
              <div className="chart-canvas chart-canvas-small">
                <Line data={pnlChart} options={pnlChartOptions} />
              </div>
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
    byTime.set(row.time, {
      source_time: row.time,
      time: compactTime(row.time),
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
    const direction = row.predicted_direction === 'down' ? 'down' : 'up'
    const countKey = `prediction_${direction}_count`
    point[countKey] = Number(point[countKey] ?? 0) + 1
  })
  payload.decision_markers.forEach((row) => {
    const point = byTime.get(row.reference_time)
    if (!point || typeof point.close !== 'number') return
    const action = row.action === 'buy' || row.action === 'sell' ? row.action : 'hold'
    point[`${action}_marker`] = point.close
    point[`${action}_count`] = Number(point[`${action}_count`] ?? 0) + 1
  })
  return Array.from(byTime.values())
}

function buildPriceChart(points: ChartPoint[]): ChartData<'line', Array<number | null>, string> {
  const labels = points.map((point) => String(point.time))
  const datasets: ChartDatasetExtra[] = [
    lineDataset('close', points, '#f4c744', 1.4),
    ...PRICE_INDICATOR_KEYS.filter((key) => hasNumber(points, key)).map((key, index) => lineDataset(key, points, indicatorStroke(index), 1.2, index % 2 === 1)),
    markerDataset('buy', points, '#00d084', 'triangle', 18, 0),
    markerDataset('sell', points, '#ff5b5b', 'triangle', 18, 180),
    markerDataset('hold', points, '#d8e2ea', 'circle', 12, 0),
  ]
  return { labels, datasets }
}

function buildCandlestickPlugin(points: ChartPoint[]): Plugin<'line'> {
  return {
    id: 'capmCandlesticks',
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart
      const xScale = scales.x
      const yScale = scales.y
      if (!xScale || !yScale || !chartArea || points.length < 2) return
      const candleWidth = Math.max(2, Math.min(8, (chartArea.width / points.length) * 0.55))
      ctx.save()
      ctx.lineWidth = 1
      points.forEach((point, index) => {
        const open = numericOrNull(point.open)
        const high = numericOrNull(point.high)
        const low = numericOrNull(point.low)
        const close = numericOrNull(point.close)
        if (open === null || high === null || low === null || close === null) return
        const x = xScale.getPixelForValue(index)
        const highY = yScale.getPixelForValue(high)
        const lowY = yScale.getPixelForValue(low)
        const openY = yScale.getPixelForValue(open)
        const closeY = yScale.getPixelForValue(close)
        const up = close >= open
        const color = up ? '#00d084' : '#ff5b5b'
        ctx.strokeStyle = color
        ctx.fillStyle = up ? 'rgb(0 208 132 / 28%)' : 'rgb(255 91 91 / 30%)'
        ctx.beginPath()
        ctx.moveTo(x, highY)
        ctx.lineTo(x, lowY)
        ctx.stroke()
        const bodyTop = Math.min(openY, closeY)
        const bodyHeight = Math.max(2, Math.abs(openY - closeY))
        ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
        ctx.strokeRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
      })
      ctx.restore()
    },
  }
}

function buildIndicatorChart(points: ChartPoint[]): ChartData<'line', Array<number | null>, string> {
  return {
    labels: points.map((point) => String(point.time)),
    datasets: DETAIL_INDICATOR_KEYS.filter((key) => hasNumber(points, key)).map((key, index) => lineDataset(key, points, indicatorStroke(index), 1.4, index % 2 === 1)),
  }
}

function buildPnlChart(payload?: DashboardChartsResponse): ChartData<'line', Array<number | null>, string> {
  const rows = payload?.pnl_curve ?? []
  if (!rows.length) return { labels: [], datasets: [] }
  return {
    labels: rows.map((row) => compactTime(row.time)),
    datasets: [
      {
        label: 'cumulative_realized_pnl_usdt',
        data: rows.map((row) => row.cumulative_realized_pnl_usdt),
        borderColor: '#00d084',
        backgroundColor: '#00d084',
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.15,
      },
    ],
  }
}

function lineDataset(label: string, points: ChartPoint[], color: string, width: number, dashed = false): ChartDatasetExtra {
  return {
    label,
    data: points.map((point) => numericOrNull(point[label])),
    borderColor: color,
    backgroundColor: color,
    borderWidth: width,
    borderDash: dashed ? [6, 5] : undefined,
    pointRadius: 0,
    pointHoverRadius: label === 'close' ? 3 : 0,
    spanGaps: true,
    tension: 0.12,
  }
}

function markerDataset(
  action: 'buy' | 'sell' | 'hold',
  points: ChartPoint[],
  color: string,
  style: 'circle' | 'triangle',
  radius: number,
  rotation: number,
): ChartDatasetExtra {
  return {
    label: action,
    markerKind: 'decision',
    data: points.map((point) => numericOrNull(point[`${action}_marker`])),
    borderColor: color,
    backgroundColor: color,
    borderWidth: 0,
    showLine: false,
    pointStyle: style,
    pointRadius: (context) => (context.raw === null ? 0 : radius),
    pointHoverRadius: (context) => (context.raw === null ? 0 : radius + 5),
    pointHitRadius: (context) => (context.raw === null ? 0 : Math.max(radius + 10, 24)),
    pointRotation: rotation,
    spanGaps: false,
  }
}

function numericOrNull(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function hasNumber(points: ChartPoint[], key: string) {
  return points.some((point) => typeof point[key] === 'number')
}

function indicatorStroke(index: number) {
  return ['#4fc3f7', '#b65cff', '#ff9800', '#26a69a', '#7e57c2'][index % 5]
}

function baseOptions(extra?: Partial<ChartOptions<'line'>>): ChartOptions<'line'> {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    normalized: true,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    elements: {
      point: {
        hitRadius: 4,
      },
    },
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#d8e2ea',
          boxWidth: 12,
          boxHeight: 12,
          usePointStyle: true,
          filter: (item) => item.text !== 'hold',
        },
      },
      tooltip: {
        enabled: true,
        displayColors: true,
        backgroundColor: '#102131',
        borderColor: '#f4c744',
        borderWidth: 1,
        titleColor: '#f4c744',
        bodyColor: '#fff',
        padding: 10,
        mode: 'index',
        intersect: false,
        filter: (item) => item.parsed.y !== null && item.dataset.label !== 'hold',
        callbacks: {
          label: tooltipLabel,
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#b6c5d1',
          maxTicksLimit: 8,
          autoSkip: true,
        },
        grid: {
          display: false,
        },
      },
      y: {
        ticks: {
          color: '#b6c5d1',
          callback: (value) => formatNumber(Number(value), 2),
        },
        grid: {
          color: '#314454',
        },
      },
    },
    ...extra,
  }
}

const priceChartOptions: ChartOptions<'line'> = baseOptions({
  plugins: {
    legend: {
      position: 'bottom',
      labels: {
        color: '#d8e2ea',
        boxWidth: 12,
        boxHeight: 12,
        usePointStyle: true,
      },
    },
    tooltip: {
      backgroundColor: '#102131',
      borderColor: '#f4c744',
      borderWidth: 1,
      titleColor: '#f4c744',
      bodyColor: '#fff',
      padding: 10,
      mode: 'index',
      intersect: false,
      filter: (item) => item.parsed.y !== null && ['close', 'buy', 'sell'].includes(String(item.dataset.label)),
      callbacks: {
        label: tooltipLabel,
      },
    },
  },
})

const indicatorChartOptions: ChartOptions<'line'> = baseOptions()
const pnlChartOptions: ChartOptions<'line'> = baseOptions()

function tooltipLabel(item: TooltipItem<'line'>) {
  const label = item.dataset.label ?? ''
  return `${label}: ${formatNumber(item.parsed.y, 4)}`
}
