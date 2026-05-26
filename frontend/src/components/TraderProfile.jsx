const SETUP_LABELS = {
  support: 'แนวรับ',
  resistance: 'แนวต้าน',
  double_bottom: 'Double Bottom',
  double_top: 'Double Top',
  triple_bottom: 'Triple Bottom',
  triple_top: 'Triple Top',
  rounded_bottom: 'Rounded Bottom',
  rounded_top: 'Rounded Top',
  price_cluster: 'Price Cluster',
  other: 'Other',
}

function biasLabel(bias) {
  if (bias === 'bullish') return 'Bullish'
  if (bias === 'bearish') return 'Bearish'
  return bias
}

function buildNarrative(summary) {
  const { dominant_setup, dominant_bias, dominant_entry, dominant_fib, total_tagged } = summary
  if (total_tagged < 3) return null

  const parts = []
  if (dominant_setup) parts.push(SETUP_LABELS[dominant_setup] || dominant_setup)
  if (dominant_bias) parts.push(biasLabel(dominant_bias))
  if (dominant_entry) parts.push(`entry ${dominant_entry}`)
  if (dominant_fib) parts.push(`near ${dominant_fib}`)
  if (parts.length === 0) return null

  return `คุณมักเล่น ${parts.join(' + ')}`
}

function winRateColor(rate) {
  if (rate === null || rate === undefined) return 'text-gray-500'
  if (rate >= 0.6) return 'text-green-400'
  if (rate >= 0.4) return 'text-yellow-400'
  return 'text-red-400'
}

function CandidateRow({ candidate }) {
  const pct = Math.min((candidate.count / candidate.threshold) * 100, 100)
  const winRate = candidate.win_rate !== null ? `${Math.round(candidate.win_rate * 100)}%` : '-'
  const label = [
    SETUP_LABELS[candidate.setup_pattern] || candidate.setup_pattern,
    candidate.trade_bias ? biasLabel(candidate.trade_bias) : null,
  ].filter(Boolean).join(' + ')

  return (
    <div className="flex items-center gap-2 py-1">
      <span className="w-40 truncate text-xs text-gray-300">{label}</span>
      <div className="h-1.5 flex-1 rounded-full bg-gray-700">
        <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 text-right text-xs text-gray-400">
        {candidate.count}/{candidate.threshold}
      </span>
      <span className={`w-8 text-right text-xs ${winRateColor(candidate.win_rate)}`}>
        {winRate}
      </span>
    </div>
  )
}

function Stat({ label, value, isString }) {
  let display = '—'
  if (isString) display = value
  else if (value != null) display = `฿${Math.round(Number(value)).toLocaleString()}`
  return (
    <div>
      <div className="text-text-dim">{label}</div>
      <div className="font-mono text-text-primary">{display}</div>
    </div>
  )
}

export default function TraderProfile({ data, account, error }) {
  if (error || !data) return null

  const { summary, candidates } = data
  const narrative = buildNarrative(summary)

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h2 className="mb-3 text-sm font-semibold text-gray-400">Trader Profile</h2>
      <div className="mb-3 grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs border-b border-border-default pb-3">
        <Stat label="Balance" value={account?.balance} />
        <Stat label="Margin" value={account?.margin} />
        <Stat label="Free margin" value={account?.free_margin} />
        <Stat label="Margin level" value={
          account && Number(account.margin) > 0
            ? `${((Number(account.equity) / Number(account.margin)) * 100).toFixed(1)}%`
            : '—'
        } isString />
      </div>
      <div className="mb-3">
        {narrative ? (
          <>
            <p className="text-sm text-gray-100">"{narrative}"</p>
            <p className="mt-1 text-xs text-gray-500">
              {summary.total_tagged} tagged trades
              {summary.rescue_rate > 0 && ` · rescue rate ${Math.round(summary.rescue_rate * 100)}%`}
            </p>
          </>
        ) : (
          <p className="text-xs text-gray-500">
            Tag trades เพิ่มเพื่อดู profile ของคุณ (ต้องการอย่างน้อย 3 trades)
          </p>
        )}
      </div>

      {candidates.length > 0 && (
        <div className="border-t border-gray-800 pt-3">
          <p className="mb-2 text-xs text-gray-500">Phase 2 Candidates</p>
          {candidates.map((candidate, index) => (
            <CandidateRow
              key={`${candidate.setup_pattern}-${candidate.trade_bias}-${index}`}
              candidate={candidate}
            />
          ))}
        </div>
      )}
    </div>
  )
}
