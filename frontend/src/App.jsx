import { useCallback, useState } from 'react'
import { usePolling } from './hooks/usePolling'
import AccountBar from './components/AccountBar'
import AlertsPanel from './components/AlertsPanel'
import InsightsPanel from './components/InsightsPanel'
import FibPanel from './components/FibPanel'
import OpenPositions from './components/OpenPositions'
import ClosedTrades from './components/ClosedTrades'
import DailyPLPanel from './components/DailyPLPanel'
import PnlChart from './components/PnlChart'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const [closedLimit, setClosedLimit] = useState(20)
  const [closedOffset, setClosedOffset] = useState(0)
  const [dailyDays, setDailyDays] = useState(14)

  const fetchAccount = useCallback(() => get('/api/account'), [])
  const fetchAlerts = useCallback(() => get('/api/alerts'), [])
  const fetchInsights = useCallback(() => get('/api/insights'), [])
  const fetchDailyPL = useCallback(() => get(`/api/daily-pl?days=${dailyDays}`), [dailyDays])
  const fetchOpen = useCallback(() => get('/api/trades?state=open'), [])
  const fetchClosed = useCallback(
    () => get(`/api/trades?state=closed&limit=${closedLimit}&offset=${closedOffset}`),
    [closedLimit, closedOffset]
  )
  const fetchPnl = useCallback(() => get('/api/trades/pnl-history?days=30'), [])
  const fetchFib = useCallback(() => get('/api/fib-levels'), [])

  const account = usePolling(fetchAccount)
  const alerts = usePolling(fetchAlerts)
  const insights = usePolling(fetchInsights)
  const dailyPL = usePolling(fetchDailyPL)
  const openTrades = usePolling(fetchOpen)
  const closedTrades = usePolling(fetchClosed)
  const pnlHistory = usePolling(fetchPnl)
  const fib = usePolling(fetchFib)

  const acknowledgeAlert = useCallback(async (id) => {
    try {
      const res = await fetch(`${API}/api/alerts/${id}/acknowledge`, { method: 'PATCH' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }, [alerts.refetch])

  const acknowledgeAll = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/alerts/acknowledge-all`, { method: 'POST' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }, [alerts.refetch])

  const handleTradeTagged = useCallback(() => {
    openTrades.refetch()
  }, [openTrades.refetch])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 space-y-4">
      <AccountBar data={account.data} error={account.error} lastUpdated={account.lastUpdated} />
      <DailyPLPanel
        data={dailyPL.data}
        error={dailyPL.error}
        days={dailyDays}
        onDaysChange={setDailyDays}
      />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <AlertsPanel
          data={alerts.data}
          error={alerts.error}
          onAcknowledge={acknowledgeAlert}
          onAcknowledgeAll={acknowledgeAll}
        />
        <InsightsPanel data={insights.data} error={insights.error} />
        <FibPanel data={fib.data?.[0]} accountData={account.data} error={fib.error} />
      </div>
      <OpenPositions
        data={openTrades.data}
        error={openTrades.error}
        onTradeTagged={handleTradeTagged}
      />
      <ClosedTrades
        data={closedTrades.data}
        error={closedTrades.error}
        limit={closedLimit}
        onLimitChange={setClosedLimit}
        offset={closedOffset}
        onOffsetChange={setClosedOffset}
      />
      <PnlChart data={pnlHistory.data} error={pnlHistory.error} />
    </div>
  )
}
