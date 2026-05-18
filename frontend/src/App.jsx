import { useCallback } from 'react'
import { usePolling } from './hooks/usePolling'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const fetchAccount = useCallback(() => get('/api/account'), [])
  const fetchAlerts = useCallback(() => get('/api/alerts'), [])
  const fetchInsights = useCallback(() => get('/api/insights'), [])
  const fetchOpen = useCallback(() => get('/api/trades?state=open'), [])
  const fetchClosed = useCallback(() => get('/api/trades?state=closed&limit=20'), [])

  const account = usePolling(fetchAccount)
  const alerts = usePolling(fetchAlerts)
  const insights = usePolling(fetchInsights)
  const openTrades = usePolling(fetchOpen)
  const closedTrades = usePolling(fetchClosed)

  async function acknowledgeAlert(id) {
    try {
      const res = await fetch(`${API}/api/alerts/${id}/acknowledge`, { method: 'PATCH' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 space-y-4">
      <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
        Account: {account.data ? JSON.stringify(account.data) : account.error ? 'error' : 'loading...'}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
          Alerts: {alerts.data?.length ?? '...'}
        </div>
        <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
          Insights: {insights.data?.length ?? '...'}
        </div>
      </div>
      <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
        Open trades: {openTrades.data?.length ?? '...'}
      </div>
      <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
        Closed trades: {closedTrades.data?.length ?? '...'}
      </div>
    </div>
  )
}
