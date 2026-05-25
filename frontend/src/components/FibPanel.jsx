import React from 'react'

const RESISTANCE_KEYS = ['R10', 'R9', 'R8', 'R7', 'R6', 'R5', 'R4', 'R3', 'R2', 'R1']
const SUPPORT_KEYS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10']
const RATIO_MAP = {
  'R1': '0.235', 'R2': '0.382', 'R3': '0.500', 'R4': '0.618', 'R5': '0.728', 'R6': '1.000', 'R7': '1.235', 'R8': '1.328', 'R9': '1.500', 'R10': '1.618',
  'S1': '0.235', 'S2': '0.382', 'S3': '0.500', 'S4': '0.618', 'S5': '0.728', 'S6': '1.000', 'S7': '1.235', 'S8': '1.328', 'S9': '1.500', 'S10': '1.618',
  'PP': '0.000'
}

function fmt(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toFixed(digits)
}

function resolveCurrentPrice(accountData) {
  return accountData?.bid ?? accountData?.ask ?? accountData?.current_price ?? null
}

function isNear(price, level) {
  if (price == null || level == null) return false
  return Math.abs(Number(price) - Number(level)) <= 5.0
}

function LevelRow({ label, value, currentPrice, colorClass }) {
  const near = isNear(currentPrice, value)
  const ratio = RATIO_MAP[label] || ''
  return (
    <div className={`grid grid-cols-[3rem_3rem_1fr] items-center rounded px-2 py-0.5 text-xs ${near ? 'bg-yellow-500/30 text-yellow-100 animate-pulse font-bold' : colorClass}`}>
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-600 text-left">{ratio}</span>
      <span className="text-right font-mono">{fmt(value)}</span>
    </div>
  )
}

export default function FibPanel({ data, error, accountData }) {
  if (!data) {
    return (
      <div className="bg-gray-900 rounded-lg p-4 min-h-72">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Fibonacci (Daily PP)</h2>
          {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
        </div>
        <p className="text-sm text-gray-600">Waiting for EA data</p>
      </div>
    )
  }

  const p_high  = Number(data.prev_high)
  const p_low   = Number(data.prev_low)
  const p_close = Number(data.prev_close)
  const pp      = Number(data.pp)
  const range   = p_high - p_low
  const price   = resolveCurrentPrice(accountData)

  return (
    <div className="bg-gray-900 rounded-lg p-4 min-h-72">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Fibonacci (Daily PP)</h2>
        <span className="text-xs px-1.5 py-0.5 rounded font-mono bg-indigo-900 text-indigo-300">
          Daily
        </span>
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs mb-3">
        <span className="text-gray-500">PP <span className="text-gray-300 font-mono">{fmt(pp)}</span></span>
        <span className="text-gray-500">Range <span className="text-gray-300 font-mono">{fmt(range)} pts</span></span>
        <span className="text-gray-500">Prev Close <span className="text-gray-300 font-mono">{fmt(p_close)}</span></span>
        <span className="text-gray-500">Day <span className="text-gray-300 font-mono">Previous</span></span>
      </div>

      <div className="space-y-0.5 font-mono text-xs">
        <p className="text-gray-600 text-[10px] uppercase tracking-wider px-2">▲ Resistance</p>
        {RESISTANCE_KEYS.map(key => (
          <LevelRow key={`r-${key}`} label={key} value={data.resistance?.[key]}
            currentPrice={price} colorClass="text-green-400" />
        ))}

        <div className={`grid grid-cols-[3rem_3rem_1fr] items-center border-y border-gray-700 px-2 py-1 my-1 ${isNear(price, pp) ? 'bg-yellow-500/30 text-yellow-100 animate-pulse font-bold' : 'text-gray-300'}`}>
          <span className="text-gray-500">PP</span>
          <span className="text-gray-600 text-left">0.000</span>
          <span className="text-right font-mono">{fmt(pp)}</span>
        </div>

        <p className="text-gray-600 text-[10px] uppercase tracking-wider px-2">▼ Support</p>
        {SUPPORT_KEYS.map(key => (
          <LevelRow key={`s-${key}`} label={key} value={data.support?.[key]}
            currentPrice={price} colorClass="text-red-400" />
        ))}
      </div>
    </div>
  )
}
