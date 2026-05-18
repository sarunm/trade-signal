const TYPE_COLORS = {
  time_bias: 'bg-purple-900 text-purple-200',
  session_bias: 'bg-indigo-900 text-indigo-200',
  pattern_win_rate: 'bg-teal-900 text-teal-200',
}

export default function InsightsPanel({ data, error }) {
  const insights = (data ?? []).slice().sort((a, b) => b.confidence - a.confidence)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Insights</h2>
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      <div className="space-y-2 max-h-72 overflow-y-auto">
        {insights.map(insight => (
          <div key={insight.id} className="p-2 rounded bg-gray-800">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${TYPE_COLORS[insight.type] ?? 'bg-gray-700 text-gray-200'}`}>
                {insight.type}
              </span>
              <span className="text-xs text-green-400 font-semibold ml-auto">
                {(insight.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-300">{insight.description}</p>
            <p className="text-xs text-gray-600 mt-0.5">n={insight.sample_size}</p>
          </div>
        ))}
        {insights.length === 0 && (
          <p className="text-sm text-gray-600">No insights yet</p>
        )}
      </div>
    </div>
  )
}
