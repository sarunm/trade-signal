const STATUS_COLOR = {
  active: 'bg-emerald-500',
  near: 'bg-amber-400',
  far: 'bg-gray-500',
  idle: 'bg-gray-700',
}

function ago(iso) {
  if (!iso) return '—'
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000) return 'just now'
  if (ms < 3600_000) return `${Math.floor(ms / 60_000)}m ago`
  if (ms < 86_400_000) return `${Math.floor(ms / 3600_000)}h ago`
  return `${Math.floor(ms / 86_400_000)}d ago`
}

export default function SignalTrail({ signals }) {
  if (!signals) return <div className="text-xs text-gray-500">Signals: loading…</div>
  if (signals.length === 0) return <div className="text-xs text-gray-500">Signals: none yet</div>

  const latest = signals[0]
  const dots = signals.slice(0, 20).slice().reverse()

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">Signal Trail (last {dots.length})</div>
      <div className="flex gap-1">
        {dots.map((s) => (
          <span
            key={s.id}
            title={`${s.status} · match ${(Number(s.match_pct) * 100).toFixed(0)}%`}
            className={`w-2 h-2 rounded-full ${STATUS_COLOR[s.status] || STATUS_COLOR.idle}`}
          />
        ))}
      </div>
      <div className="text-xs text-gray-500">
        Last: {ago(latest.emitted_at)} · match {(Number(latest.match_pct) * 100).toFixed(0)}%
        {latest.missing_conditions?.length > 0 && (
          <span> · missing: {latest.missing_conditions.join(', ')}</span>
        )}
      </div>
    </div>
  )
}
