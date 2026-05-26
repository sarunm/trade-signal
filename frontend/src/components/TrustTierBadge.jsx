const TIER_META = {
  ea_candidate: { label: '🎯 EA Candidate', cls: 'bg-yellow-600 text-yellow-50' },
  live_proven: { label: '★ Live Proven', cls: 'bg-emerald-700 text-emerald-50' },
  validated: { label: '✓ Validated', cls: 'bg-blue-700 text-blue-50' },
  experimental: { label: '🧪 Experimental', cls: 'bg-gray-700 text-gray-200' },
}

export default function TrustTierBadge({ tier }) {
  const meta = TIER_META[tier] || TIER_META.experimental
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${meta.cls}`}>
      {meta.label}
    </span>
  )
}

export const TIER_RANK = {
  ea_candidate: 4,
  live_proven: 3,
  validated: 2,
  experimental: 1,
}
