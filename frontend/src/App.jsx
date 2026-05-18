import { useCallback } from 'react'
import { usePolling } from './hooks/usePolling'
import AccountBar from './components/AccountBar'
import AlertsPanel from './components/AlertsPanel'
import InsightsPanel from './components/InsightsPanel'

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

  const acknowledgeAlert = useCallback(async (id) => {
    try {
      const res = await fetch(`${API}/api/alerts/${id}/acknowledge`, { method: 'PATCH' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }, [alerts.refetch])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 space-y-4">
      <AccountBar data={account.data} error={account.error} lastUpdated={account.lastUpdated} />
      <div className="grid grid-cols-2 gap-4">
        <AlertsPanel data={alerts.data} error={alerts.error} onAcknowledge={acknowledgeAlert} />
        <InsightsPanel data={insights.data} error={insights.error} />
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
