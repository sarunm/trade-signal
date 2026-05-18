import { useState, useEffect } from 'react'

function fmt(v, decimals = 2) {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

export default function AccountBar({ data, error, lastUpdated }) {
  const [secs, setSecs] = useState(0)

  useEffect(() => {
    setSecs(0)
    const id = setInterval(() => {
      setSecs(lastUpdated ? Math.floor((new Date() - lastUpdated) / 1000) : 0)
    }, 1000)
    return () => clearInterval(id)
  }, [lastUpdated])

  const floatPL = data?.floating_pl != null ? Number(data.floating_pl) : null

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Account</h2>
        <span className={`text-xs ${error ? 'text-red-400' : 'text-gray-500'}`}>
          {error ? 'Data may be stale' : lastUpdated ? `Updated ${secs}s ago` : 'Loading...'}
        </span>
      </div>
      <div className="grid grid-cols-5 gap-6">
        {[
          { label: 'Equity', value: fmt(data?.equity) },
          { label: 'Balance', value: fmt(data?.balance) },
          { label: 'Margin', value: fmt(data?.margin) },
          { label: 'Free Margin', value: fmt(data?.free_margin) },
          { label: 'Float P/L', value: fmt(data?.floating_pl), colored: true },
        ].map(({ label, value, colored }) => (
          <div key={label}>
            <p className="text-xs text-gray-500 mb-0.5">{label}</p>
            <p className={`text-xl font-mono font-semibold ${
              colored && floatPL != null
                ? floatPL >= 0 ? 'text-green-400' : 'text-red-400'
                : 'text-white'
            }`}>
              {value === '—' ? value : `$${value}`}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
