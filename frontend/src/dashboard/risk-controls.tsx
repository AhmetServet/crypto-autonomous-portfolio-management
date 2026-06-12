import { Shield } from 'lucide-react'

import { Panel } from './primitives'
import type { RiskPreset, RiskSettings } from './risk-settings'

export function RiskControlsPanel({
  preset,
  settings,
  onPresetChange,
  onSettingsChange,
}: {
  preset: RiskPreset
  settings: RiskSettings
  onPresetChange: (preset: RiskPreset) => void
  onSettingsChange: (settings: RiskSettings) => void
}) {
  const update = (patch: Partial<RiskSettings>) => onSettingsChange({ ...settings, ...patch })

  return (
    <Panel title="Risk Controls" icon={<Shield size={17} />}>
      <div className="control-grid three">
        <div className="control-form">
          <h3>Preset</h3>
          <label>
            Risk Preset
            <select value={preset} onChange={(event) => onPresetChange(event.target.value as RiskPreset)}>
              <option value="conservative">conservative</option>
              <option value="normal">normal</option>
              <option value="aggressive">aggressive</option>
            </select>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={settings.emergencyStop}
              onChange={(event) => update({ emergencyStop: event.target.checked })}
            />
            Emergency stop
          </label>
        </div>
        <div className="control-form wide">
          <h3>Limits</h3>
          <div className="form-grid">
            <label>Max Trade USDT<input type="number" min="0.01" step="0.01" value={settings.maxTradeUsdt} onChange={(event) => update({ maxTradeUsdt: Number(event.target.value) })} /></label>
            <label>Max Position USDT<input type="number" min="0.01" step="0.01" value={settings.maxPositionUsdt} onChange={(event) => update({ maxPositionUsdt: Number(event.target.value) })} /></label>
            <label>Max Daily Loss USDT<input type="number" min="0.01" step="0.01" value={settings.maxDailyLossUsdt} onChange={(event) => update({ maxDailyLossUsdt: Number(event.target.value) })} /></label>
            <label>Max Orders Per Day<input type="number" min="1" step="1" value={settings.maxOrdersPerDay} onChange={(event) => update({ maxOrdersPerDay: Number(event.target.value) })} /></label>
            <label>Cooldown Minutes<input type="number" min="0" step="1" value={settings.cooldownMinutes} onChange={(event) => update({ cooldownMinutes: Number(event.target.value) })} /></label>
            <label>Max Exposure USDT<input type="number" min="0.01" step="0.01" value={settings.maxExposureUsdt} onChange={(event) => update({ maxExposureUsdt: Number(event.target.value) })} /></label>
            <label>Min Predicted Return<input type="number" step="0.0001" value={settings.minPredictedReturn} onChange={(event) => update({ minPredictedReturn: Number(event.target.value) })} /></label>
            <label>Prediction Staleness Minutes<input type="number" min="1" step="1" value={settings.predictionStalenessMinutes} onChange={(event) => update({ predictionStalenessMinutes: Number(event.target.value) })} /></label>
          </div>
        </div>
      </div>
    </Panel>
  )
}
