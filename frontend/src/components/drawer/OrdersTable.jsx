function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function fmtPrice(n) {
  if (n == null) return '—'
  return Number(n).toFixed(2)
}

function fmtBaht(n, signed = true) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = signed && v >= 0 ? '+' : ''
  return `${sign}฿${Math.round(v).toLocaleString()}`
}

export default function OrdersTable({ title, trades, mode }) {
  if (!trades) return <div className="text-xs text-gray-500">{title}: loading…</div>
  if (trades.length === 0) return <div className="text-xs text-gray-500">{title}: none</div>

  const rows = mode === 'history' ? trades.slice(0, 20) : trades

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">{title}</div>
      <div className={mode === 'history' ? 'max-h-40 overflow-y-auto' : ''}>
        <table className="w-full text-xs">
          <tbody>
            {rows.map((t) => {
              const isWin = (Number(t.profit) || 0) > 0
              const tone = mode === 'active'
                ? 'text-gray-300'
                : isWin ? 'text-emerald-400' : 'text-red-400'
              return (
                <tr key={t.id} className="border-b border-gray-900">
                  <td className="py-1 pr-2">#{t.ticket}</td>
                  <td className="py-1 pr-2 uppercase">{t.direction}</td>
                  <td className="py-1 pr-2 text-gray-500">
                    {mode === 'active' ? `open ${fmtTime(t.open_time)}` : `close ${fmtTime(t.close_time)}`}
                  </td>
                  <td className="py-1 pr-2 text-gray-500">@{fmtPrice(t.open_price)}</td>
                  <td className={`py-1 pr-2 ${tone}`}>{fmtBaht(t.profit)}</td>
                  <td className="py-1 text-gray-500">{t.paper_exit_reason || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
