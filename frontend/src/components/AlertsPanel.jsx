const TYPE_COLORS = {
  equity_buffer: 'bg-red-900 text-red-200',
  double_down: 'bg-yellow-900 text-yellow-200',
  consecutive_loss: 'bg-orange-900 text-orange-200',
  pattern_alert: 'bg-blue-900 text-blue-200',
}

const TF_ORDER = ['W1', 'D', 'H4', 'H1', 'M30', 'M15', 'M5']
const tfRank = tf => { const i = TF_ORDER.indexOf(tf); return i === -1 ? 99 : i }

function DirectionArrow({ direction }) {
  if (direction === 'bullish') return <span className="text-green-400 font-bold shrink-0">↑</span>
  if (direction === 'bearish') return <span className="text-red-400 font-bold shrink-0">↓</span>
  return null
}

function AlertRow({ alert, onAcknowledge, muted }) {
  const colorClass = TYPE_COLORS[alert.type] ?? 'bg-gray-800 text-gray-200'
  const direction = alert.trigger_data?.direction
  return (
    <div className={`flex items-start gap-2 p-2 rounded ${muted ? 'opacity-40' : ''}`}>
      <DirectionArrow direction={direction} />
      <span className={`text-xs px-1.5 py-0.5 rounded font-mono shrink-0 ${colorClass}`}>
        {alert.type}
      </span>
      <p className="text-sm text-gray-300 flex-1 min-w-0 break-words">{alert.message}</p>
      {!muted && onAcknowledge && (
        <button
          onClick={() => onAcknowledge(alert.id)}
          className="text-xs text-gray-500 hover:text-white shrink-0 px-1"
        >
          Ack
        </button>
      )}
    </div>
  )
}

export default function AlertsPanel({ data, error, onAcknowledge }) {
  const alerts = data ?? []
  const unacked = alerts.filter(a => !a.acknowledged)
  const acked = alerts.filter(a => a.acknowledged)

  // Pattern alerts: group by TF, largest TF first, latest 3 per group
  const patternUnacked = unacked.filter(a => a.type === 'pattern_alert')
  const otherUnacked = unacked.filter(a => a.type !== 'pattern_alert')

  const byTF = {}
  patternUnacked.forEach(a => {
    const tf = a.trigger_data?.timeframe ?? 'unknown'
    if (!byTF[tf]) byTF[tf] = []
    byTF[tf].push(a)
  })
  const sortedTFs = Object.keys(byTF).sort((a, b) => tfRank(a) - tfRank(b))

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Alerts</h2>
        {unacked.length > 0 && (
          <span className="bg-red-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
            {unacked.length}
          </span>
        )}
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      <div className="space-y-3 max-h-72 overflow-y-auto">
        {/* Pattern alerts grouped by TF, largest first, max 3 each */}
        {sortedTFs.map(tf => (
          <div key={tf}>
            <p className="text-xs text-gray-500 font-semibold uppercase mb-1 px-2">{tf}</p>
            <div className="space-y-1">
              {byTF[tf]
                .slice()
                .sort((a, b) => new Date(b.sent_at) - new Date(a.sent_at))
                .slice(0, 3)
                .map(alert => (
                  <AlertRow key={alert.id} alert={alert} onAcknowledge={onAcknowledge} />
                ))}
            </div>
          </div>
        ))}
        {/* Non-pattern alerts */}
        {otherUnacked.length > 0 && (
          <div className="space-y-1">
            {otherUnacked.map(alert => (
              <AlertRow key={alert.id} alert={alert} onAcknowledge={onAcknowledge} />
            ))}
          </div>
        )}
        {/* Acknowledged */}
        {acked.map(alert => (
          <AlertRow key={alert.id} alert={alert} muted />
        ))}
        {alerts.length === 0 && (
          <p className="text-sm text-gray-600">No alerts</p>
        )}
      </div>
    </div>
  )
}
