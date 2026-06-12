import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cpu, Eye, Play, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { TrainingJob, TrainingType } from '../api'
import { cancelTrainingJob, createTrainingJob, getTrainingJob, getTrainingJobs, getTrainingPresets } from '../api'
import { compactTime } from './format'
import { EmptyState, MutationResult, Panel } from './primitives'

function buildTrainingConfig({
  trainingType,
  modelName,
  symbol,
  interval,
  start,
  calibration,
  split,
  end,
  forecastHorizon,
  buyThreshold,
}: {
  trainingType: TrainingType
  modelName: string
  symbol: string
  interval: string
  start: string
  calibration: string
  split: string
  end: string
  forecastHorizon: number
  buyThreshold: number
}) {
  if (trainingType === 'deep_learning') {
    return {
      symbol,
      interval,
      model_name: modelName,
      start_time: start,
      split_time: split,
      end_time: end,
      sequence_length: 60,
      forecast_horizon: forecastHorizon,
      target_field: 'close',
      target_mode: 'return',
      scaler: 'zscore',
      artifacts_dir: 'experiments/results',
      model_parameters: {
        hidden_size: 32,
        num_layers: 1,
        dropout: 0,
        learning_rate: 0.001,
        batch_size: 128,
        max_epochs: 5,
        weight_decay: 0,
        seed: 42,
        device: 'auto',
      },
      backtest: {
        starting_cash: 10000,
        buy_threshold: buyThreshold,
        commission_rate: 0.001,
        cash_fraction: 0.95,
      },
    }
  }
  if (trainingType === 'statistical') {
    return {
      description: `Dashboard ${modelName} walk-forward training.`,
      init_schema: false,
      symbol,
      interval,
      model_name: modelName,
      model_parameters: modelName === 'arima'
        ? { order: [1, 0, 0], fit_kwargs: {} }
        : { daily_seasonality: true, weekly_seasonality: false, yearly_seasonality: false },
      target_field: 'close',
      window_size: modelName === 'arima' ? 720 : 240,
      forecast_horizon: forecastHorizon,
      start_time: start,
      end_time: end,
      validation_size: 1,
      step_size: 240,
      required_features: [],
      artifacts_dir: 'experiments/results',
      backtest: {
        enabled: true,
        starting_cash: 10000,
        buy_threshold: buyThreshold,
      },
    }
  }
  return {
    description: `Dashboard ${modelName} production training.`,
    symbol,
    interval,
    model_name: modelName,
    model_parameters: modelName === 'lightgbm'
      ? {
          n_estimators: 120,
          max_depth: 4,
          learning_rate: 0.05,
          subsample: 0.8,
          colsample_bytree: 0.9,
          objective: 'regression',
          random_state: 42,
          n_jobs: -1,
          verbosity: -1,
        }
      : {
          n_estimators: 100,
          max_depth: 4,
          learning_rate: 0.05,
          subsample: 0.8,
          colsample_bytree: 0.9,
          objective: 'reg:squarederror',
          tree_method: 'hist',
          random_state: 42,
          n_jobs: -1,
        },
    target_field: 'close',
    target_mode: 'return',
    forecast_horizon: forecastHorizon,
    start_time: start,
    calibration_time: calibration,
    split_time: split,
    end_time: end,
    required_features: [],
    starting_cash: 10000,
    buy_threshold: buyThreshold,
    commission_rate: 0.001,
    cash_fraction: 0.95,
    artifacts_dir: 'experiments/results',
  }
}

function firstPresetModelName(config: Record<string, unknown>, fallback: string) {
  if (typeof config.model_name === 'string') return config.model_name
  const models = Array.isArray(config.models) ? config.models : []
  const firstModel = models.find((item): item is Record<string, unknown> => item !== null && typeof item === 'object')
  return typeof firstModel?.model_name === 'string' ? firstModel.model_name : fallback
}

function applyTrainingFormValues(
  config: Record<string, unknown>,
  {
    modelName,
    symbol,
    interval,
    start,
    calibration,
    split,
    end,
    forecastHorizon,
    buyThreshold,
  }: {
    modelName: string
    symbol: string
    interval: string
    start: string
    calibration: string
    split: string
    end: string
    forecastHorizon: number
    buyThreshold: number
  },
) {
  const next: Record<string, unknown> = {
    ...config,
    symbol,
    interval,
    start_time: start,
    end_time: end,
    forecast_horizon: forecastHorizon,
  }
  const models = Array.isArray(next.models) ? next.models : null
  if (models) {
    const selectedModels = models.filter(
      (item) => item !== null && typeof item === 'object' && (item as Record<string, unknown>).model_name === modelName,
    )
    if (selectedModels.length) next.models = selectedModels
  } else if ('model_name' in next) {
    next.model_name = modelName
  }
  if ('split_time' in next) next.split_time = split
  if ('calibration_time' in next) next.calibration_time = calibration
  const backtest = next.backtest
  if (backtest && typeof backtest === 'object' && !Array.isArray(backtest)) {
    next.backtest = { ...backtest, buy_threshold: buyThreshold }
  } else {
    next.buy_threshold = buyThreshold
  }
  return next
}

export function TrainingPanel({
  symbol,
  interval,
  onCompleted,
}: {
  symbol: string
  interval: string
  onCompleted: () => void
}) {
  const queryClient = useQueryClient()
  const [trainingType, setTrainingType] = useState<TrainingType>('tabular')
  const [modelName, setModelName] = useState('xgboost')
  const [trainSymbol, setTrainSymbol] = useState(symbol)
  const [trainInterval, setTrainInterval] = useState(interval)
  const [start, setStart] = useState('2023-03-24T14:00:00Z')
  const [calibration, setCalibration] = useState('2026-05-15T22:32:00Z')
  const [split, setSplit] = useState('2026-05-25T00:00:00Z')
  const [end, setEnd] = useState(new Date().toISOString())
  const [forecastHorizon, setForecastHorizon] = useState(15)
  const [buyThreshold, setBuyThreshold] = useState(0.0002)
  const [selectedPresetPath, setSelectedPresetPath] = useState('')
  const [selectedPresetConfig, setSelectedPresetConfig] = useState<Record<string, unknown> | null>(null)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)

  const presetsQuery = useQuery({ queryKey: ['training-presets'], queryFn: getTrainingPresets })
  const jobsQuery = useQuery({ queryKey: ['training-jobs'], queryFn: getTrainingJobs, refetchInterval: 5_000 })
  const selectedJobQuery = useQuery({
    queryKey: ['training-job', selectedJobId],
    queryFn: () => getTrainingJob(String(selectedJobId)),
    enabled: selectedJobId !== null,
    refetchInterval: selectedJobId ? 3_000 : false,
  })

  const generatedConfig = useMemo(() => {
    if (selectedPresetConfig) {
      return applyTrainingFormValues(selectedPresetConfig, {
        modelName,
        symbol: trainSymbol,
        interval: trainInterval,
        start,
        calibration,
        split,
        end,
        forecastHorizon,
        buyThreshold,
      })
    }
    return buildTrainingConfig({
      trainingType,
      modelName,
      symbol: trainSymbol,
      interval: trainInterval,
      start,
      calibration,
      split,
      end,
      forecastHorizon,
      buyThreshold,
    })
  }, [buyThreshold, calibration, end, forecastHorizon, modelName, selectedPresetConfig, split, start, trainInterval, trainSymbol, trainingType])

  const createMutation = useMutation({
    mutationFn: () => createTrainingJob({
      training_type: trainingType,
      name: `${trainSymbol}-${trainInterval}-${modelName}`,
      config: generatedConfig,
    }),
    onSuccess: (data) => {
      setSelectedJobId(data.job.id)
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['model-artifacts'] })
      onCompleted()
    },
  })
  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => cancelTrainingJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['training-job'] })
    },
  })

  const availableModels = trainingType === 'deep_learning'
    ? ['lstm', 'gru']
    : trainingType === 'statistical'
      ? ['arima', 'prophet']
      : ['xgboost', 'lightgbm']
  const jobs = jobsQuery.data?.jobs ?? []
  const selectedJob = selectedJobQuery.data?.job ?? jobs.find((job) => job.id === selectedJobId)

  return (
    <Panel title="Training UI" icon={<Cpu size={17} />}>
      <div className="control-grid three">
        <form className="control-form wide" onSubmit={(event) => { event.preventDefault(); createMutation.mutate() }}>
          <h3>Train Model</h3>
          <div className="form-grid">
            <label>
              Preset
              <select
                value={selectedPresetPath}
                onChange={(event) => {
                  setSelectedPresetPath(event.target.value)
                  if (!event.target.value) {
                    setSelectedPresetConfig(null)
                    return
                  }
                  const preset = presetsQuery.data?.presets.find((item) => item.path === event.target.value)
                  if (!preset) return
                  const fallbackModelName = preset.training_type === 'deep_learning' ? 'lstm' : preset.training_type === 'statistical' ? 'arima' : 'xgboost'
                  setTrainingType(preset.training_type)
                  setModelName(firstPresetModelName(preset.config, fallbackModelName))
                  setTrainSymbol(String(preset.symbol ?? trainSymbol))
                  setTrainInterval(String(preset.interval ?? trainInterval))
                  setStart(String(preset.config.start_time ?? start))
                  setCalibration(String(preset.config.calibration_time ?? preset.config.split_time ?? calibration))
                  setSplit(String(preset.config.split_time ?? split))
                  setEnd(String(preset.config.end_time ?? end))
                  setForecastHorizon(Number(preset.config.forecast_horizon ?? forecastHorizon))
                  const backtest = preset.config.backtest as Record<string, unknown> | undefined
                  setBuyThreshold(Number(backtest?.buy_threshold ?? preset.config.buy_threshold ?? buyThreshold))
                  setSelectedPresetConfig(preset.config)
                }}
              >
                <option value="">manual builder</option>
                {(presetsQuery.data?.presets ?? []).map((preset) => (
                  <option key={preset.path} value={preset.path}>{`${preset.training_type} / ${preset.name}`}</option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select
                value={trainingType}
                onChange={(event) => {
                  const next = event.target.value as TrainingType
                  setSelectedPresetPath('')
                  setSelectedPresetConfig(null)
                  setTrainingType(next)
                  setModelName(next === 'deep_learning' ? 'lstm' : next === 'statistical' ? 'arima' : 'xgboost')
                }}
              >
                <option value="tabular">tabular</option>
                <option value="deep_learning">deep_learning</option>
                <option value="statistical">statistical</option>
              </select>
            </label>
            <label>Model<select value={modelName} onChange={(event) => setModelName(event.target.value)}>{availableModels.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label>Symbol<input value={trainSymbol} onChange={(event) => setTrainSymbol(event.target.value)} /></label>
            <label>Interval<input value={trainInterval} onChange={(event) => setTrainInterval(event.target.value)} /></label>
            <label>Forecast Horizon<input type="number" min="1" value={forecastHorizon} onChange={(event) => setForecastHorizon(Number(event.target.value))} /></label>
            <label>Buy Threshold<input type="number" step="0.0001" value={buyThreshold} onChange={(event) => setBuyThreshold(Number(event.target.value))} /></label>
            <label>Start<input value={start} onChange={(event) => setStart(event.target.value)} /></label>
            <label>Calibration<input value={calibration} onChange={(event) => setCalibration(event.target.value)} /></label>
            <label>Split<input value={split} onChange={(event) => setSplit(event.target.value)} /></label>
            <label>End<input value={end} onChange={(event) => setEnd(event.target.value)} /></label>
          </div>
          <button type="submit" disabled={createMutation.isPending}>
            <Play size={15} />
            Start Training
          </button>
        </form>

        <div className="control-form">
          <h3>Generated Config</h3>
          <pre>{JSON.stringify(generatedConfig, null, 2)}</pre>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Created</th>
              <th>Name</th>
              <th>Type</th>
              <th>Status</th>
              <th>PID</th>
              <th>Return</th>
              <th>Config</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job: TrainingJob) => (
              <tr key={job.id}>
                <td>{compactTime(job.created_at)}</td>
                <td>{job.name}</td>
                <td>{job.training_type}</td>
                <td><span className={`badge ${job.status === 'succeeded' ? 'good' : 'neutral'}`}>{job.status}</span></td>
                <td>{job.pid ?? '-'}</td>
                <td>{job.return_code ?? '-'}</td>
                <td className="truncate">{job.config_path}</td>
                <td className="actions">
                  <button type="button" className="icon-button" title="View logs" onClick={() => setSelectedJobId(job.id)}>
                    <Eye size={15} />
                  </button>
                  {job.status === 'running' ? (
                    <button type="button" className="icon-button" title="Cancel" onClick={() => cancelMutation.mutate(job.id)}>
                      <X size={15} />
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!jobs.length ? <EmptyState message={jobsQuery.isFetching ? 'Loading training jobs...' : 'No dashboard training jobs in this API process.'} /> : null}
      {selectedJob ? (
        <div className="result-block">
          <h3>{`Training Log / ${selectedJob.name}`}</h3>
          <pre>{selectedJob.log ?? 'Loading log...'}</pre>
        </div>
      ) : null}
      <MutationResult title="Training Result" data={createMutation.data} error={createMutation.error} />
      <MutationResult title="Cancel Result" data={cancelMutation.data} error={cancelMutation.error} />
    </Panel>
  )
}
