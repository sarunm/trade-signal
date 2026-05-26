const GATE_LABELS = {
  sample: 'sample',
  performance: 'performance',
  stability: 'stability',
  walk_forward: 'walk_forward',
}

export default function PromotionGates({ gates, ruleId }) {
  if (!gates) return <div className="text-xs text-gray-500">Gates: loading…</div>
  const entry = (gates.rules || []).find((r) => r.rule_id === ruleId)
  if (!entry) return <div className="text-xs text-gray-500">Gates: no data for this rule</div>

  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-400">Promotion Gates</div>
      <div className="flex gap-3 text-xs flex-wrap">
        {Object.entries(GATE_LABELS).map(([key, label]) => {
          const passed = entry.gates?.[key] === true
          return (
            <span key={key} className={passed ? 'text-emerald-400' : 'text-red-400'}>
              {passed ? '✓' : '✗'} {label}
            </span>
          )
        })}
      </div>
      <div className="text-xs text-gray-500">
        tier: <span className="text-gray-300">{entry.tier}</span>
        {entry.reason && <span> · {entry.reason}</span>}
      </div>
    </div>
  )
}
