const TYPE_COLORS = {
  equity_buffer: 'bg-red-900 text-red-200',
  double_down: 'bg-yellow-900 text-yellow-200',
  consecutive_loss: 'bg-orange-900 text-orange-200',
  pattern_alert: 'bg-blue-900 text-blue-200',
}

function AlertRow({ alert, onAcknowledge, muted }) {
  const colorClass = TYPE_COLORS[alert.type] ?? 'bg-gray-800 text-gray-200'
  return (
    <div className={`flex items-start gap-2 p-2 rounded ${muted ? 'opacity-40' : ''}`}>
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
      <div className="space-y-1 max-h-72 overflow-y-auto">
        {unacked.map(alert => (
          <AlertRow key={alert.id} alert={alert} onAcknowledge={onAcknowledge} />
        ))}
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
