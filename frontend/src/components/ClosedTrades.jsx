function fmt(v, d = 5) {
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

function fmtExit(reason) {
  return reason ? reason.toUpperCase() : '—'
}

export default function ClosedTrades({ data, error }) {
  const trades = data ?? []
  const real = trades.filter(t => !t.is_paper)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Recent Closed Trades
        </h2>
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      {real.length === 0 ? (
        <p className="text-sm text-gray-600">No closed trades yet</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 text-left border-b border-gray-800">
              <th className="pb-2 pr-4">Ticket</th>
              <th className="pb-2 pr-4">Dir</th>
              <th className="pb-2 pr-4">Entry</th>
              <th className="pb-2 pr-4">Exit Price</th>
              <th className="pb-2 pr-4">Real P/L</th>
              <th className="pb-2 pr-4">Paper P/L</th>
              <th className="pb-2 pr-4">Exit</th>
              <th className="pb-2">Diff</th>
            </tr>
          </thead>
          <tbody>
            {real.map(t => {
              const paper = trades.find(p => p.is_paper && p.ticket === t.ticket)
              const realPL = t.profit != null ? Number(t.profit) : null
              const paperPL = paper?.profit != null ? Number(paper.profit) : null
              const diff = realPL != null && paperPL != null ? paperPL - realPL : null
              return (
                <tr key={t.ticket} className="border-b border-gray-800 last:border-0">
                  <td className="py-2 pr-4 font-mono text-gray-300">{t.ticket}</td>
                  <td className={`py-2 pr-4 font-semibold ${t.direction === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                    {t.direction?.toUpperCase() ?? '—'}
                  </td>
                  <td className="py-2 pr-4 font-mono text-gray-400">{fmt(t.open_price)}</td>
                  <td className="py-2 pr-4 font-mono text-gray-400">{fmt(t.close_price)}</td>
                  <td className={`py-2 pr-4 font-mono ${plColor(realPL)}`}>{fmtPL(realPL)}</td>
                  <td className={`py-2 pr-4 font-mono ${plColor(paperPL)}`}>{fmtPL(paperPL)}</td>
                  <td className="py-2 pr-4 font-semibold text-gray-300">{fmtExit(paper?.paper_exit_reason)}</td>
                  <td className={`py-2 font-mono ${plColor(diff)}`}>{fmtPL(diff)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
