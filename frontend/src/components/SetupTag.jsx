const API = 'http://localhost:8000'

const PATTERNS = [
  { value: '', label: '— pattern' },
  { value: 'double_bottom', label: 'Double Bottom' },
  { value: 'double_top', label: 'Double Top' },
  { value: 'triple_bottom', label: 'Triple Bottom' },
  { value: 'triple_top', label: 'Triple Top' },
  { value: 'rounded_bottom', label: 'Rounded Bottom' },
  { value: 'rounded_top', label: 'Rounded Top' },
  { value: 'price_cluster', label: 'Price Cluster' },
  { value: 'other', label: 'Other' },
]

const BIASES = [
  { value: '', label: '— bias' },
  { value: 'bullish', label: 'Bullish' },
  { value: 'bearish', label: 'Bearish' },
]

export default function SetupTag({
  ticket,
  currentPattern,
  currentBias,
  nearFibLevel,
  entryCandle,
  onUpdated,
}) {
  async function handleChange(field, value) {
    try {
      const body = { [field]: value || null }
      const res = await fetch(`${API}/api/trades/${ticket}/tag`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok && onUpdated) onUpdated(await res.json())
    } catch (_) {}
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-1">
        <select
          className="text-xs bg-gray-800 text-gray-300 rounded px-1 py-0.5 border border-gray-700"
          value={currentPattern ?? ''}
          onChange={e => handleChange('setup_pattern', e.target.value)}
        >
          {PATTERNS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select
          className="text-xs bg-gray-800 text-gray-300 rounded px-1 py-0.5 border border-gray-700"
          value={currentBias ?? ''}
          onChange={e => handleChange('trade_bias', e.target.value)}
        >
          {BIASES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <div className="flex gap-2 text-xs text-gray-500">
        {nearFibLevel && <span>near {nearFibLevel}</span>}
        {entryCandle && entryCandle !== 'none' && <span>{entryCandle}</span>}
      </div>
    </div>
  )
}
