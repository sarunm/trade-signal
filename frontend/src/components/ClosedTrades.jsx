function fmt(v, d = 2) {
  if (v == null) return '—'
  return Number(v).toFixed(d)
}

function fmtPL(v) {
  if (v == null) return '—'
  const n = Number(v)
  return (n >= 0 ? '+' : '') + n.toFixed(2)
}

function plColor(v) {
  if (v == null) return 'text-gray-500'
  return Number(v) >= 0 ? 'text-green-400' : 'text-red-400'
}

export default function ClosedTrades({ data, error, limit, onLimitChange, offset, onOffsetChange }) {
  const trades = data ?? []
  const real = trades.filter(t => !t.is_paper)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Recent Closed Trades
        </h2>
        <div className="ml-auto flex items-center gap-2">
          <select
            className="text-xs bg-gray-800 text-gray-300 rounded px-1 py-0.5 border border-gray-700"
            value={limit}
            onChange={e => { onLimitChange(Number(e.target.value)); onOffsetChange(0) }}
          >
            {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          {offset > 0 && (
            <button
              className="text-xs text-gray-400 hover:text-white px-1"
              onClick={() => onOffsetChange(Math.max(0, offset - limit))}
            >← Prev</button>
          )}
          {real.length === limit && (
            <button
              className="text-xs text-gray-400 hover:text-white px-1"
              onClick={() => onOffsetChange(offset + limit)}
            >Next →</button>
          )}
        </div>
        {error && <span className="text-xs text-red-400">Stale</span>}
      </div>
      {real.length === 0 ? (
        <p className="text-sm text-gray-600">No closed trades yet</p>
      ) : (
        <div className="space-y-2">
          {real.map(t => {
            const paper = trades.find(p => p.is_paper && p.ticket === t.ticket)
            const realPL = t.profit != null ? Number(t.profit) : null
            const paperPL = paper?.profit != null ? Number(paper.profit) : null
            const diff = realPL != null && paperPL != null ? paperPL - realPL : null
            const dir = t.direction?.toUpperCase() ?? '—'
            const dirColor = t.direction === 'buy' ? 'text-green-400' : 'text-red-400'
            return (
              <div key={t.ticket} className="bg-gray-800 rounded px-3 py-2 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-gray-400 text-xs">#{t.ticket}</span>
                  <span className={`font-semibold text-xs ${dirColor}`}>{dir}</span>
                  {t.setup_pattern && (
                    <span className="text-xs text-gray-500">{t.setup_pattern}</span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-1 text-xs">
                  <div className="flex gap-2">
                    <span className="text-gray-500">Real</span>
                    <span className="font-mono text-gray-400">{fmt(t.open_price, 2)}</span>
                    <span className="text-gray-600">→</span>
                    <span className="font-mono text-gray-400">{fmt(t.close_price, 2)}</span>
                    <span className={`font-mono ${plColor(realPL)}`}>{fmtPL(realPL)}</span>
                  </div>
                  {paper && (
                    <div className="flex gap-2">
                      <span className="text-gray-500">Paper</span>
                      <span className="font-mono text-gray-400">{fmt(paper.open_price, 2)}</span>
                      <span className="text-gray-600">→</span>
                      <span className="font-mono text-gray-400">{fmt(paper.close_price, 2)}</span>
                      <span className={`font-mono ${plColor(paperPL)}`}>{fmtPL(paperPL)}</span>
                      {diff != null && (
                        <span className={`font-mono ${plColor(diff)}`}>Δ{fmtPL(diff)}</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
