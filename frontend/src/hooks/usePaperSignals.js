import { useCallback, useEffect, useRef, useState } from 'react'
import { usePolling } from './usePolling'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function usePaperRules() {
  const fetcher = useCallback(() => get('/api/paper-trader-rules?status=active'), [])
  return usePolling(fetcher, 5000)
}

export function usePatternsById() {
  const fetcher = useCallback(() => get('/api/patterns'), [])
  const { data, ...rest } = usePolling(fetcher, 30000)
  const byId = {}
  for (const p of data || []) byId[p.id] = p
  return { byId, ...rest }
}

const NOTIFY_TIERS = new Set(['live_proven', 'ea_candidate'])
const NOTIFY_STATUSES = new Set(['near', 'active'])

export function usePaperSignalNotifications(rules) {
  const lastSeen = useRef({})
  useEffect(() => {
    if (typeof Notification === 'undefined') return
    if (Notification.permission === 'default') Notification.requestPermission()
  }, [])

  useEffect(() => {
    if (!rules) return
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'granted') return
    for (const r of rules) {
      if (!NOTIFY_TIERS.has(r.trust_tier)) continue
      if (!NOTIFY_STATUSES.has(r.last_signal_status)) continue
      if (lastSeen.current[r.id] === r.last_signal_status) continue
      lastSeen.current[r.id] = r.last_signal_status
      new Notification(`${r.mode} signal ${r.last_signal_status}`, {
        body: `Trust: ${r.trust_tier} · Net EV: ฿${Number(r.net_ev_per_trade ?? 0).toFixed(0)}`,
        tag: `paper-rule-${r.id}-${r.last_signal_status}`,
      })
    }
  }, [rules])
}

export function usePaperRuleDetail(ruleId, patternId) {
  const [data, setData] = useState({
    trades: null,
    signals: null,
    shadows: null,
    gates: null,
  })
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const refetch = useCallback(async () => {
    if (!ruleId) return
    setLoading(true)
    setError(null)
    try {
      const [trades, signals, shadows, gates] = await Promise.all([
        get(`/api/paper-trades?rule_id=${ruleId}`),
        get(`/api/paper-signals?rule_id=${ruleId}&limit=20`),
        get(`/api/paper-trader-rules/${ruleId}/shadows`),
        patternId ? get(`/api/patterns/${patternId}/gates`) : Promise.resolve(null),
      ])
      setData({ trades, signals, shadows, gates })
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }, [ruleId, patternId])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { data, error, loading, refetch }
}
