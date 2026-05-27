import React from 'react'

const TYPE_LABEL = {
  buy_limit: 'BUY LIMIT',
  sell_limit: 'SELL LIMIT',
  buy_stop: 'BUY STOP',
  sell_stop: 'SELL STOP',
}

function fmt(v, d = 2) {
  if (v == null) return '—'
  return Number(v).toFixed(d)
}

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-GB', {
    month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function distance(pendingPrice, currentPrice) {
  if (pendingPrice == null || currentPrice == null) return null
  return Number(pendingPrice) - Number(currentPrice)
}

export default function PendingOrders({ data, error, currentPrice }) {
  const pending = (data ?? []).filter(t => !t.is_paper)

  return (
    <div className="bg-card border border-border-default rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-text-dim uppercase tracking-wider">
          Pending Orders
        </h2>
        {pending.length > 0 && (
          <span className="text-xs text-text-dim">{pending.length} pending</span>
        )}
        {error && <span className="text-xs text-loss ml-auto">Stale</span>}
      </div>
      {pending.length === 0 ? (
        <p className="text-sm text-text-dim">No pending orders</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-text-dim text-left border-b border-border-default">
              <th className="pb-2 pr-4">Ticket</th>
              <th className="pb-2 pr-4">Type</th>
              <th className="pb-2 pr-4">Pending price</th>
              <th className="pb-2 pr-4">Distance</th>
              <th className="pb-2">Placed</th>
            </tr>
          </thead>
          <tbody>
            {pending.map(t => {
              const dist = distance(t.pending_price, currentPrice)
              const tone =
                t.order_type === 'buy_limit' || t.order_type === 'buy_stop'
                  ? 'text-profit'
                  : 'text-loss'
              return (
                <tr key={t.id} className="border-b border-border-default last:border-0">
                  <td className="py-2 pr-4 font-mono text-text-primary">{t.ticket}</td>
                  <td className={`py-2 pr-4 font-semibold ${tone}`}>
                    {TYPE_LABEL[t.order_type] ?? t.order_type?.toUpperCase()}
                  </td>
                  <td className="py-2 pr-4 font-mono">{fmt(t.pending_price)}</td>
                  <td className={`py-2 pr-4 font-mono ${dist == null ? '' : dist >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {dist == null ? '—' : `${dist >= 0 ? '+' : ''}${dist.toFixed(2)}`}
                  </td>
                  <td className="py-2 text-xs text-text-dim">{fmtTime(t.open_time)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
