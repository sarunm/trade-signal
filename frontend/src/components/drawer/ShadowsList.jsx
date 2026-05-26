function fmtPct(n) {
  if (n == null) return '—'
  return `${(Number(n) * 100).toFixed(0)}%`
}

function fmtDelta(n) {
  if (n == null) return '—'
  const v = Number(n) * 100
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}%`
}

export default function ShadowsList({ shadows }) {
  if (!shadows) return <div className="text-xs text-gray-500">Shadows: loading…</div>
  const list = shadows.shadows || []
  if (list.length === 0) return <div className="text-xs text-gray-500">Shadows: none</div>

  const parent = shadows.parent
  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-400">Shadows ({list.length})</div>
      {list.map((s) => {
        const filterClause = (s.filters || []).map((f) => `${f.feature} ≠ ${f.exclude}`).join(', ')
        const deltaTone = s.winrate_delta == null
          ? 'text-gray-500'
          : Number(s.winrate_delta) > 0 ? 'text-emerald-400' : 'text-red-400'
        return (
          <div key={s.id} className="border border-gray-800 rounded p-2 space-y-1">
            <div className="text-xs text-amber-300">Testing: {filterClause || '—'}</div>
            <div className="text-xs text-gray-300">
              Parent WR {fmtPct(parent.winrate)} ({parent.trades})
              {' · '}
              Shadow WR {fmtPct(s.winrate)} ({s.trades})
              {' · '}
              Δ <span className={deltaTone}>{fmtDelta(s.winrate_delta)}</span>
            </div>
            <div className="text-xs text-gray-500">status: {s.status}</div>
          </div>
        )
      })}
    </div>
  )
}
