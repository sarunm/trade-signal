import { useMemo, useState } from 'react'
import PaperRuleCard from './PaperRuleCard'
import { TIER_RANK } from './TrustTierBadge'
import { usePaperRules, usePatternsById, usePaperSignalNotifications } from '../hooks/usePaperSignals'

const TIER_FILTERS = ['all', 'ea_candidate', 'live_proven', 'validated', 'experimental']

function fmtBaht(n) {
  if (n == null) return '฿0'
  const v = Number(n)
  const sign = v > 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}฿${Math.abs(Math.round(v)).toLocaleString()}`
}

export default function PaperTradeConsole() {
  const [tierFilter, setTierFilter] = useState('all')
  const rules = usePaperRules()
  const { byId: patternsById } = usePatternsById()
  usePaperSignalNotifications(rules.data)

  const sorted = useMemo(() => {
    const list = (rules.data || []).filter((r) => r.status !== 'shadow')
    list.sort((a, b) => {
      const ta = TIER_RANK[a.trust_tier] || 0
      const tb = TIER_RANK[b.trust_tier] || 0
      if (ta !== tb) return tb - ta
      const ea = Number(a.net_ev_per_trade ?? -Infinity)
      const eb = Number(b.net_ev_per_trade ?? -Infinity)
      return eb - ea
    })
    if (tierFilter !== 'all') return list.filter((r) => r.trust_tier === tierFilter)
    return list
  }, [rules.data, tierFilter])

  const totals = useMemo(() => {
    const list = (rules.data || []).filter((r) => r.status !== 'shadow')
    const today = list.reduce((s, r) => s + Number(r.paper_pnl_today ?? 0), 0)
    const week = list.reduce((s, r) => s + Number(r.paper_pnl_week ?? 0), 0)
    return { active: list.length, today, week }
  }, [rules.data])

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="text-sm text-text-dim">
          <span className="text-text-primary font-semibold">{totals.active}</span> active rules ·{' '}
          Today: <span className={totals.today >= 0 ? 'text-profit' : 'text-loss'}>{fmtBaht(totals.today)}</span> ·{' '}
          Week: <span className={totals.week >= 0 ? 'text-profit' : 'text-loss'}>{fmtBaht(totals.week)}</span>
        </div>
        <div className="flex gap-2 flex-wrap">
          {TIER_FILTERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTierFilter(t)}
              className={`px-2 py-1 text-xs rounded ${
                t === tierFilter ? 'bg-brand text-white' : 'bg-card text-text-dim'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {rules.error && <div className="text-xs text-loss">Failed to load rules</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {sorted.map((r) => (
          <PaperRuleCard key={r.id} rule={r} pattern={patternsById[r.pattern_id]} />
        ))}
      </div>
    </section>
  )
}
