export default function PatternConditions({ rule, pattern }) {
  const slugs = pattern?.indicator_slugs || []
  const tf = pattern?.timeframe || '—'
  const filters = rule.filters || []
  const weights = rule.score_weights || null

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">Pattern Conditions</div>
      <div className="text-xs text-gray-300">
        Indicators: {slugs.length ? slugs.map((s) => `${s} (${tf})`).join(', ') : '—'}
      </div>
      <div className="text-xs text-gray-300">
        Filters:{' '}
        {filters.length === 0
          ? <span className="text-gray-500">none</span>
          : filters.map((f, i) => (
              <span key={i} className="ml-1 inline-block rounded bg-gray-800 px-1">
                {f.feature} ≠ {f.exclude}
              </span>
            ))}
      </div>
      {weights && (
        <div className="text-xs text-gray-300">
          Score weights:{' '}
          {Object.entries(weights).map(([k, v]) => `${k} ${v}`).join(', ')}
        </div>
      )}
    </div>
  )
}
