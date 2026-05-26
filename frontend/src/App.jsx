import { useCallback, useState, useMemo } from 'react'
import { usePolling } from './hooks/usePolling'
import { useTradeAlerts } from './hooks/useTradeAlerts'
import TopBar from './components/TopBar'
import SectionDivider from './components/SectionDivider'
import AlertsPanel from './components/AlertsPanel'
import InsightsPanel from './components/InsightsPanel'
import TraderProfile from './components/TraderProfile'
import OpenPositions from './components/OpenPositions'
import ClosedTrades from './components/ClosedTrades'
import PnlChart from './components/PnlChart'
import TradeAdvisor from './components/TradeAdvisor'
import PaperTradeConsole from './components/PaperTradeConsole'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const [closedLimit, setClosedLimit] = useState(20)
  const [closedOffset, setClosedOffset] = useState(0)

  const fetchHeader = useCallback(() => get('/api/header-snapshot'), [])
  const fetchAccount = useCallback(() => get('/api/account'), [])
  const fetchAlerts = useCallback(() => get('/api/alerts'), [])
  const fetchInsights = useCallback(() => get('/api/insights'), [])
  const fetchOpen = useCallback(() => get('/api/trades?state=open'), [])
  const fetchClosed = useCallback(
    () => get(`/api/trades?state=closed&limit=${closedLimit}&offset=${closedOffset}`),
    [closedLimit, closedOffset]
  )
  const fetchPnl = useCallback(() => get('/api/trades/pnl-history?days=30'), [])
  const fetchTraderProfile = useCallback(() => get('/api/trader-profile'), [])
  const fetchAdvisor = useCallback(() => get('/api/trade-advisor'), [])

  const header = usePolling(fetchHeader, 1000)
  const account = usePolling(fetchAccount, 3000)
  const alerts = usePolling(fetchAlerts)
  const insights = usePolling(fetchInsights)
  const openTrades = usePolling(fetchOpen)
  const closedTrades = usePolling(fetchClosed)
  const pnlHistory = usePolling(fetchPnl)
  const traderProfile = usePolling(fetchTraderProfile, 60000)
  const advisor = usePolling(fetchAdvisor)
  useTradeAlerts()

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

  const handleTradeTagged = useCallback(() => openTrades.refetch(), [openTrades.refetch])

  const alertCount = useMemo(
    () => (alerts.data ?? []).filter(a => !a.acknowledged_at).length,
    [alerts.data]
  )

  const scrollToAlerts = useCallback(() => {
    const el = document.getElementById('alerts-anchor')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  return (
    <div className="min-h-screen bg-base text-text-primary">
      <TopBar
        accountId={header.data?.account_id ?? account.data?.account_id}
        balance={header.data?.balance ?? account.data?.balance}
        equity={header.data?.equity ?? account.data?.equity}
        todayPnlBaht={header.data?.today_pnl_baht}
        todayPnlPct={header.data?.today_pnl_pct}
        floatPl={header.data?.floating_pl ?? account.data?.floating_pl}
        xauPrice={header.data?.xau_price}
        alertCount={alertCount}
        eaOnline={header.data?.ea_online ?? false}
        onAlertsClick={scrollToAlerts}
      />
      <main className="px-4 pb-8">
        <SectionDivider label="Real Trading" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-7">
            <OpenPositions
              data={openTrades.data}
              error={openTrades.error}
              onTradeTagged={handleTradeTagged}
            />
          </div>
          <div className="lg:col-span-5">
            <TradeAdvisor data={advisor.data} />
          </div>
        </div>
        <div id="alerts-anchor" className="grid grid-cols-1 lg:grid-cols-12 gap-4 mt-4">
          <div className="lg:col-span-6">
            <AlertsPanel
              data={alerts.data}
              error={alerts.error}
              onAcknowledge={acknowledgeAlert}
              onAcknowledgeAll={acknowledgeAll}
            />
          </div>
          <div className="lg:col-span-6">
            <InsightsPanel data={insights.data} error={insights.error} />
          </div>
        </div>

        <SectionDivider label="Paper Lab" />
        <PaperTradeConsole />

        <SectionDivider label="History" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-7">
            <ClosedTrades
              data={closedTrades.data}
              error={closedTrades.error}
              limit={closedLimit}
              onLimitChange={setClosedLimit}
              offset={closedOffset}
              onOffsetChange={setClosedOffset}
            />
          </div>
          <div className="lg:col-span-5">
            <PnlChart data={pnlHistory.data} error={pnlHistory.error} />
          </div>
        </div>
        <div className="mt-4">
          <TraderProfile data={traderProfile.data} account={account.data} error={traderProfile.error} />
        </div>
      </main>
    </div>
  )
}
