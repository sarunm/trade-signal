function fmtBaht(n, withSign = true) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = withSign && v >= 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}฿${Math.abs(Math.round(v)).toLocaleString()}`
}

function fmtPct(n) {
  if (n == null) return ''
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

export default function TopBar({
  equity,
  todayPnlBaht,
  todayPnlPct,
  floatPl,
  xauPrice,
  alertCount = 0,
  eaOnline = false,
  onAlertsClick,
}) {
  const todayTone = (todayPnlBaht ?? 0) >= 0 ? 'text-profit' : 'text-loss'
  const floatTone = (floatPl ?? 0) >= 0 ? 'text-profit' : 'text-loss'

  return (
    <div className="sticky top-0 z-50 h-14 bg-surface border-b border-border-default flex items-center px-4 gap-6">
      <div className="flex items-center gap-4 text-sm">
        <span className="font-mono text-text-primary">฿{Math.round(Number(equity ?? 0)).toLocaleString()}</span>
        <span className={`font-mono ${todayTone}`}>
          {fmtBaht(todayPnlBaht)} ({fmtPct(todayPnlPct)})
        </span>
        <span className="text-text-dim">
          Float: <span className={`font-mono ${floatTone}`}>{fmtBaht(floatPl)}</span>
        </span>
      </div>
      <div className="flex-1 text-center">
        <span className="font-mono text-neutral text-base">
          XAUUSD {xauPrice != null ? Number(xauPrice).toFixed(2) : '—'}
        </span>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <button
          type="button"
          onClick={onAlertsClick}
          className="relative px-2 py-1 rounded hover:bg-card"
        >
          🔔
          {alertCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-loss text-white text-xs px-1.5 rounded-full">
              {alertCount}
            </span>
          )}
        </button>
        <span className={`flex items-center gap-1 ${eaOnline ? 'text-profit' : 'text-text-dim'}`}>
          EA<span className={`w-2 h-2 rounded-full ${eaOnline ? 'bg-profit' : 'bg-text-dim'}`} />
        </span>
      </div>
    </div>
  )
}
