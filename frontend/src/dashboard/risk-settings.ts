export type RiskPreset = 'conservative' | 'normal' | 'aggressive'

export type RiskSettings = {
  emergencyStop: boolean
  maxTradeUsdt: number
  maxPositionUsdt: number
  maxDailyLossUsdt: number
  maxOrdersPerDay: number
  cooldownMinutes: number
  maxExposureUsdt: number
  minPredictedReturn: number
  predictionStalenessMinutes: number
}

export const RISK_PRESETS: Record<RiskPreset, RiskSettings> = {
  conservative: {
    emergencyStop: false,
    maxTradeUsdt: 10,
    maxPositionUsdt: 50,
    maxDailyLossUsdt: 20,
    maxOrdersPerDay: 8,
    cooldownMinutes: 15,
    maxExposureUsdt: 50,
    minPredictedReturn: 0.001,
    predictionStalenessMinutes: 3,
  },
  normal: {
    emergencyStop: false,
    maxTradeUsdt: 25,
    maxPositionUsdt: 100,
    maxDailyLossUsdt: 50,
    maxOrdersPerDay: 20,
    cooldownMinutes: 5,
    maxExposureUsdt: 100,
    minPredictedReturn: 0.0005,
    predictionStalenessMinutes: 5,
  },
  aggressive: {
    emergencyStop: false,
    maxTradeUsdt: 50,
    maxPositionUsdt: 250,
    maxDailyLossUsdt: 100,
    maxOrdersPerDay: 60,
    cooldownMinutes: 1,
    maxExposureUsdt: 250,
    minPredictedReturn: 0.0002,
    predictionStalenessMinutes: 10,
  },
}
