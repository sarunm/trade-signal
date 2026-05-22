function fmtMoney(v) {
  if (v == null) return '—'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}฿${n.toFixed(2)}`
}

function fmtPct(v) {
  if (v == null) return '—'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function fmtBalance(v) {
  if (v == null) return '—'
  return `฿${Number(v).toFixed(2)}`
}

function plColor(v) {
  if (v == null) return 'text-gray-500'
  return Number(v) >= 0 ? 'text-green-400' : 'text-red-400'
}

function fmtDate(v) {
  if (!v) return '—'
  return new Date(`${v}T00:00:00`).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
  })
}

export default function DailyPLPanel({ data, error, days, onDaysChange }) {
  const rows = data ?? []

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Daily P/L
        </h2>
        <select
          className="ml-auto text-xs bg-gray-800 text-gray-300 rounded px-1 py-0.5 border border-gray-700"
          value={days}
          onChange={e => onDaysChange(Number(e.target.value))}
        >
          {[7, 14, 30, 90].map(n => <option key={n} value={n}>{n}d</option>)}
        </select>
        {error && <span className="text-xs text-red-400">Stale</span>}
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-gray-600">No closed trades yet</p>
      ) : (
        <div className="overflow-x-auto max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-900">
              <tr className="text-xs text-gray-500 text-left border-b border-gray-800">
                <th className="pb-2 pr-4">Date</th>
                <th className="pb-2 pr-4 text-right">P/L</th>
                <th className="pb-2 pr-4 text-right">%</th>
                <th className="pb-2 pr-4 text-right">Trades</th>
                <th className="pb-2 text-right">Base</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.date} className="border-b border-gray-800 last:border-0">
                  <td className="py-2 pr-4 text-gray-300">{fmtDate(row.date)}</td>
                  <td className={`py-2 pr-4 text-right font-mono font-semibold ${plColor(row.profit)}`}>
                    {fmtMoney(row.profit)}
                  </td>
                  <td className={`py-2 pr-4 text-right font-mono ${plColor(row.profit)}`}>
                    {fmtPct(row.profit_pct)}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono text-gray-400">
                    {row.trade_count}
                  </td>
                  <td className="py-2 text-right font-mono text-gray-500">
                    {fmtBalance(row.base_balance)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
