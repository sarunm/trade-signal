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
      {rule.shadow_of_rule_id ? (
        <div className="text-xs text-amber-300">
          🌗 Shadow of <code className="text-amber-200">{rule.shadow_of_rule_id.slice(0, 8)}</code> — testing:
          {(rule.filters || []).map((f, i) => (
            <span key={i} className="ml-1 inline-block rounded bg-amber-900/40 px-1">
              {f.feature}≠{f.exclude}
            </span>
          ))}
        </div>
      ) : (rule.filters || []).length > 0 ? (
        <div className="text-xs text-gray-400">
          Filters:
          {rule.filters.map((f, i) => (
            <span key={i} className="ml-1 inline-block rounded bg-gray-800 px-1">
              {f.feature}≠{f.exclude}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}
