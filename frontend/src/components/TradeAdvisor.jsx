const VERDICT_CONFIG = {
  good:      { label: 'Good entry',  cls: 'text-green-400' },
  caution:   { label: 'Caution',     cls: 'text-yellow-400' },
  high_risk: { label: 'High risk',   cls: 'text-red-400' },
}

function RecoveryMap({ plan }) {
  const { tp, add, cut, entry_price } = plan
  return (
    <div className="text-sm mt-3 space-y-1">
      <div className="text-green-400 font-semibold text-xs uppercase tracking-wide">TP Targets</div>
      {[...tp].reverse().map(z => (
        <div key={z.label} className="flex justify-between px-2 text-green-300">
          <span className="w-8">{z.label}</span>
          <span>{z.price.toFixed(2)}</span>
          <span className="text-right w-20">+{Math.abs(z.pts).toFixed(0)} pts</span>
        </div>
      ))}
      <div className="border-t border-gray-600 my-1 text-center text-xs text-gray-500">
        entry {entry_price.toFixed(2)}
      </div>
      <div className="text-red-400 font-semibold text-xs uppercase tracking-wide">Add Zones</div>
      {add.map(z => (
        <div key={z.label} className="flex justify-between px-2 text-red-300">
          <span className="w-8">{z.label}</span>
          <span>{z.price.toFixed(2)}</span>
          <span className="text-right w-20">{z.pts.toFixed(0)} pts</span>
        </div>
      ))}
      <div className="flex justify-between px-2 mt-2 text-orange-400 font-semibold">
        <span>Cut if {cut.label} breached</span>
        <span>{cut.price.toFixed(2)}</span>
        <span className="text-right w-20">{cut.pts.toFixed(0)} pts</span>
      </div>
    </div>
  )
}

function TradeCard({ trade }) {
  const { direction, open_price, entry_score, entry_verdict, recovery_plan } = trade
  const verdict = VERDICT_CONFIG[entry_verdict] || { label: 'Pending', cls: 'text-gray-400' }

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex justify-between items-center">
        <span className="font-bold">
          {direction?.toUpperCase()} @ {open_price?.toFixed(2)}
        </span>
        <span className={`font-bold ${verdict.cls}`}>
          {entry_score != null ? `Score: ${entry_score}  ` : ''}{verdict.label}
        </span>
      </div>
      {recovery_plan
        ? <RecoveryMap plan={recovery_plan} />
        : <div className="text-gray-500 text-sm mt-2">Waiting for fib data</div>
      }
    </div>
  )
}

export default function TradeAdvisor({ data }) {
  if (!data || data.length === 0) {
    return <div className="text-gray-400 text-sm p-4">No open trades</div>
  }
  return (
    <div className="space-y-3">
      {data.map(trade => <TradeCard key={trade.id} trade={trade} />)}
    </div>
  )
}
