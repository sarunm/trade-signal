import { useMemo, useState } from 'react'
import PaperRuleCard from './PaperRuleCard'
import { TIER_RANK } from './TrustTierBadge'
import { usePaperRules, usePatternsById, usePaperSignalNotifications } from '../hooks/usePaperSignals'

const TIER_FILTERS = ['all', 'ea_candidate', 'live_proven', 'validated', 'experimental']

export default function PaperTradeConsole() {
  const [tierFilter, setTierFilter] = useState('all')
  const rules = usePaperRules()
  const { byId: patternsById } = usePatternsById()
  usePaperSignalNotifications(rules.data)

  const sorted = useMemo(() => {
    const list = (rules.data || []).slice()
    list.sort((a, b) => {
      const ta = TIER_RANK[a.trust_tier] || 0
      const tb = TIER_RANK[b.trust_tier] || 0
      if (ta !== tb) return tb - ta
      const ea = Number(a.net_ev_per_trade ?? -Infinity)
      const eb = Number(b.net_ev_per_trade ?? -Infinity)
      return eb - ea
    })
    if (tierFilter !== 'all') {
      return list.filter((r) => r.trust_tier === tierFilter)
    }
    return list
  }, [rules.data, tierFilter])

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Paper Trade Console</h2>
        <div className="flex gap-2 flex-wrap">
          {TIER_FILTERS.map((t) => (
            <button
              key={t}
              onClick={() => setTierFilter(t)}
              className={`px-2 py-1 text-xs rounded ${
                t === tierFilter ? 'bg-blue-600' : 'bg-gray-800'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {rules.error && (
        <div className="text-xs text-red-400">Failed to load rules</div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {sorted.map((r) => (
          <PaperRuleCard key={r.id} rule={r} pattern={patternsById[r.pattern_id]} />
        ))}
      </div>
    </section>
  )
}
