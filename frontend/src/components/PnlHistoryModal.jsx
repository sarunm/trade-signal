import { useEffect, useState } from 'react'

const API = 'http://localhost:8000'
const TABS = [
  { key: 'all', label: 'All' },
  { key: 'daily', label: 'Daily' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
]

function fmtBaht(n) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}฿${Math.round(v).toLocaleString()}`
}

function fmtPct(n) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

export default function PnlHistoryModal({ open, onClose }) {
  const [tab, setTab] = useState('daily')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setError(null)
    fetch(`${API}/api/pnl-history?granularity=${tab}&page=${page}&page_size=20`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(json => { if (!cancelled) setData(json) })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [open, tab, page])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-surface border border-border-default rounded-lg w-full max-w-2xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-border-default">
          <h2 className="text-text-primary font-semibold">PnL History</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-text-dim hover:text-text-primary text-xl leading-none"
            aria-label="Close"
          >×</button>
        </div>
        <div className="flex gap-2 p-4 border-b border-border-default">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => { setTab(t.key); setPage(1) }}
              className={`px-3 py-1 text-xs rounded ${
                t.key === tab ? 'bg-brand text-white' : 'bg-card text-text-dim'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-auto p-4">
          {error && <div className="text-loss text-sm">Failed to load: {error}</div>}
          {!error && !data && <div className="text-text-dim text-sm">Loading…</div>}
          {data && (
            <table className="w-full text-sm">
              <thead className="text-xs text-text-dim text-left">
                <tr><th className="py-1">Period</th><th>P/L</th><th>%</th><th className="text-right">Trades</th></tr>
              </thead>
              <tbody>
                {data.items.map((row, i) => {
                  const tone = Number(row.profit) >= 0 ? 'text-profit' : 'text-loss'
                  return (
                    <tr key={`${row.period}-${i}`} className={i % 2 === 0 ? 'bg-card' : ''}>
                      <td className="py-1 px-2 text-text-primary">{row.period}</td>
                      <td className={`px-2 font-mono ${tone}`}>{fmtBaht(row.profit)}</td>
                      <td className={`px-2 font-mono ${tone}`}>{fmtPct(row.profit_pct)}</td>
                      <td className="px-2 text-right text-text-dim">{row.trade_count}</td>
                    </tr>
                  )
                })}
                {data.items.length === 0 && (
                  <tr><td colSpan={4} className="py-4 text-center text-text-dim">No data</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-center gap-3 p-3 border-t border-border-default text-sm">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              className="px-2 py-1 bg-card rounded disabled:opacity-40"
            >◀ Prev</button>
            <span className="text-text-dim">Page {data.page} / {data.total_pages}</span>
            <button
              disabled={page >= data.total_pages}
              onClick={() => setPage(p => p + 1)}
              className="px-2 py-1 bg-card rounded disabled:opacity-40"
            >Next ▶</button>
          </div>
        )}
      </div>
    </div>
  )
}
