import React from 'react'
import SetupTag from './SetupTag'

function fmt(v, d = 5) {
  if (v == null) return '—'
  return Number(v).toFixed(d)
}

function chipForScore(score, verdict) {
  if (score == null) return null
  const s = Number(score)
  let cls = 'border-loss/30 text-loss bg-loss/10'
  if (s >= 7) cls = 'border-profit/30 text-profit bg-profit/10'
  else if (s >= 4) cls = 'border-warning/30 text-warning bg-warning/10'
  const label = verdict === 'good' ? 'Good entry' : verdict === 'caution' ? 'Caution' : verdict === 'high_risk' ? 'High risk' : ''
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs ${cls}`}>
      ● {s.toFixed(1)} {label}
    </span>
  )
}

function fmtStrategy(v) {
  if (!v) return '—'
  return v
    .replaceAll('tp:', 'TP ')
    .replaceAll(';sl:', ' / SL ')
    .replaceAll('_avg', '')
    .replaceAll('_', ' ')
}

export default function OpenPositions({ data, error, onTradeTagged }) {
  const trades = data ?? []
  const real = trades.filter(t => !t.is_paper)

  return (
    <div className="bg-gray-900 rounded-lg p-4 h-full">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Open Positions
        </h2>
        {real.length > 0 && (
          <span className="text-xs text-gray-500">{real.length} open</span>
        )}
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      {real.length === 0 ? (
        <p className="text-sm text-gray-600">No open positions</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 text-left border-b border-gray-800">
              <th className="pb-2 pr-4">Ticket</th>
              <th className="pb-2 pr-4">Dir</th>
              <th className="pb-2 pr-4">Real Entry</th>
              <th className="pb-2 pr-4">Paper Entry</th>
              <th className="pb-2 pr-4">Paper SL</th>
              <th className="pb-2 pr-4">Paper TP</th>
              <th className="pb-2">Rule</th>
              <th className="pb-2 pl-2">Tag</th>
            </tr>
          </thead>
          <tbody>
            {real.map(t => {
              const paper = trades.find(p => p.is_paper && p.ticket === t.ticket)
              return (
                <React.Fragment key={t.ticket}>
                  <tr className="border-b border-gray-800 last:border-0">
                    <td className="py-2 pr-4 font-mono text-gray-300">{t.ticket}</td>
                    <td className={`py-2 pr-4 font-semibold ${t.direction === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                      {t.direction?.toUpperCase() ?? '—'}
                    </td>
                    <td className="py-2 pr-4 font-mono">{fmt(t.open_price)}</td>
                    <td className="py-2 pr-4 font-mono">{fmt(paper?.open_price)}</td>
                    <td className="py-2 pr-4 font-mono text-red-400">{fmt(paper?.sl)}</td>
                    <td className="py-2 pr-4 font-mono text-green-400">{fmt(paper?.tp)}</td>
                    <td className="py-2 text-xs text-gray-400">{fmtStrategy(paper?.paper_exit_strategy)}</td>
                    <td className="py-2 pl-2">
                      <SetupTag
                        ticket={t.ticket}
                        currentPattern={t.setup_pattern}
                        currentBias={t.trade_bias}
                        nearFibLevel={t.near_fib_level}
                        entryCandle={t.entry_candle}
                        onUpdated={onTradeTagged}
                      />
                    </td>
                  </tr>
                  {t.entry_score != null && (
                    <tr className="border-b border-gray-800 last:border-0">
                      <td colSpan={8} className="py-1 pl-1">
                        {chipForScore(t.entry_score, t.entry_verdict)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
