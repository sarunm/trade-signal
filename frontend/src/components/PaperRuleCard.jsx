import TrustTierBadge from './TrustTierBadge'

const STATUS_DOT = {
  active: 'bg-emerald-500',
  near: 'bg-amber-400',
  far: 'bg-gray-500',
  idle: 'bg-gray-700',
}

function ageChip(seconds) {
  if (!seconds || seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

export default function PaperRuleCard({ rule, pattern }) {
  const dot = STATUS_DOT[rule.last_signal_status] || STATUS_DOT.idle
  const ev = rule.net_ev_per_trade != null
    ? `฿${Number(rule.net_ev_per_trade).toFixed(0)}`
    : '—'
  const wilson = rule.wilson_lower_95 != null
    ? `${(Number(rule.wilson_lower_95) * 100).toFixed(0)}%`
    : '—'
  const baseline = rule.baseline_delta != null
    ? `${Number(rule.baseline_delta) >= 0 ? '+' : ''}${(Number(rule.baseline_delta) * 100).toFixed(1)}%`
    : '—'
  return (
    <div className="bg-gray-900 border border-gray-800 rounded p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-sm font-medium">{rule.mode}</span>
          <span className="text-xs text-gray-400">[{ageChip(rule.age_seconds)}]</span>
        </div>
        <TrustTierBadge tier={rule.trust_tier} />
      </div>
      <div className="text-xs text-gray-400">
        {pattern?.indicator_slugs?.join(' + ') || '—'}
      </div>
      <div className="flex justify-between text-xs">
        <div>Net EV: <span className="text-gray-100">{ev}</span>/trade</div>
        <div>Wilson: <span className="text-gray-100">{wilson}</span></div>
        <div>vs Baseline: <span className="text-gray-100">{baseline}</span></div>
      </div>
      <div className="text-xs text-gray-500">
        Trades {rule.total_trades} · Wins {rule.win_count}
      </div>
    </div>
  )
}
