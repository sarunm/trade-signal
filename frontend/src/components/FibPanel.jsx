const R_LEVELS = ['1.618','1.500','1.328','1.235','1.000','0.728','0.618','0.5','0.382','0.235']
const S_LEVELS = ['0.235','0.382','0.5','0.618','0.728','1.000','1.235','1.328','1.500','1.618']

function fmt(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toFixed(digits)
}

function resolveCurrentPrice(accountData) {
  return accountData?.bid ?? accountData?.ask ?? accountData?.current_price ?? null
}

function isNear(price, level, range) {
  if (price == null || level == null || !range) return false
  return Math.abs(Number(price) - Number(level)) <= range * 0.003
}

function LevelRow({ label, value, currentPrice, range, colorClass }) {
  const near = isNear(currentPrice, value, range)
  return (
    <div className={`grid grid-cols-[4.5rem_1fr] items-center rounded px-2 py-0.5 text-xs ${near ? 'bg-yellow-900/70 text-yellow-100' : colorClass}`}>
      <span className="text-gray-500">{label}</span>
      <span className="text-right font-mono">{fmt(value)}</span>
    </div>
  )
}

export default function FibPanel({ data, error, accountData }) {
  if (!data) {
    return (
      <div className="bg-gray-900 rounded-lg p-4 min-h-72">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Fibonacci (ROM)</h2>
          {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
        </div>
        <p className="text-sm text-gray-600">Waiting for EA data</p>
      </div>
    )
  }

  const phigh = Number(data.swing_high)
  const plow  = Number(data.swing_low)
  const range = phigh - plow
  const PP    = data.levels?.['0.000']
  const price = resolveCurrentPrice(accountData)

  return (
    <div className="bg-gray-900 rounded-lg p-4 min-h-72">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Fibonacci (ROM)</h2>
        <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${data.direction === 'bullish' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}>
          {data.direction === 'bullish' ? 'Bullish' : 'Bearish'}
        </span>
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs mb-3">
        <span className="text-gray-500">Prev High <span className="text-gray-300 font-mono">{fmt(phigh)}</span></span>
        <span className="text-gray-500">Prev Low <span className="text-gray-300 font-mono">{fmt(plow)}</span></span>
        <span className="text-gray-500">PP <span className="text-gray-300 font-mono">{fmt(PP)}</span></span>
        <span className="text-gray-500">Range <span className="text-gray-300 font-mono">{fmt(range)} pts</span></span>
      </div>

      <div className="space-y-0.5 font-mono text-xs">
        <p className="text-gray-600 text-[10px] uppercase tracking-wider px-2">Resistance (R)</p>
        {R_LEVELS.map(key => (
          <LevelRow key={`r-${key}`} label={key} value={data.levels?.[key]}
            currentPrice={price} range={range} colorClass="text-green-400" />
        ))}

        <div className={`grid grid-cols-[4.5rem_1fr] items-center border-y border-gray-700 px-2 py-1 my-1 ${isNear(price, PP, range) ? 'bg-yellow-900/70 text-yellow-100' : 'text-gray-300'}`}>
          <span className="text-gray-500">PP</span>
          <span className="text-right font-mono">{fmt(PP)}</span>
        </div>

        <p className="text-gray-600 text-[10px] uppercase tracking-wider px-2">Support (S)</p>
        {S_LEVELS.map(key => (
          <LevelRow key={`s-${key}`} label={key} value={data.extensions?.[key]}
            currentPrice={price} range={range} colorClass="text-red-400" />
        ))}
      </div>
    </div>
  )
}
