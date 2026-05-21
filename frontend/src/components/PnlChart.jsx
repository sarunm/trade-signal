import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

function fmtMoney(v) {
  if (v == null) return '-'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

function fmtDate(v) {
  if (!v) return '-'
  return new Date(`${v}T00:00:00`).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
  })
}

export default function PnlChart({ data, error }) {
  const rows = data ?? []
  const latest = rows.at(-1)?.cumulative_pnl ?? 0
  const lineColor = Number(latest) > 0 ? '#4ade80' : '#f87171'

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Cumulative P/L
        </h2>
        <span className={`ml-auto text-sm font-mono font-semibold ${Number(latest) > 0 ? 'text-green-400' : 'text-red-400'}`}>
          {rows.length > 0 ? fmtMoney(latest) : ''}
        </span>
        {error && <span className="text-xs text-red-400">Stale</span>}
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-gray-600">No closed trades yet</p>
      ) : (
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="#1f2937" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={fmtDate}
                tick={{ fill: '#6b7280', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                minTickGap={24}
              />
              <YAxis
                tickFormatter={fmtMoney}
                tick={{ fill: '#6b7280', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={72}
              />
              <Tooltip
                contentStyle={{
                  background: '#111827',
                  border: '1px solid #374151',
                  borderRadius: 8,
                  color: '#e5e7eb',
                }}
                formatter={value => [fmtMoney(value), 'Cumulative P/L']}
                labelFormatter={fmtDate}
              />
              <Line
                type="monotone"
                dataKey="cumulative_pnl"
                stroke={lineColor}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
