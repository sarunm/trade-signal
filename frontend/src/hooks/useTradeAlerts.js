import { useEffect, useRef } from 'react'

const ALERT_TYPES = 'tp_zone_reached,add_zone_reached,cut_zone_reached'
const API = 'http://localhost:8000'

export function useTradeAlerts() {
  const notifiedIds = useRef(new Set())

  useEffect(() => {
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission()
    }

    const poll = async () => {
      try {
        const res = await fetch(`${API}/api/alerts?unacknowledged_only=true&types=${ALERT_TYPES}`)
        if (!res.ok) return
        const alerts = await res.json()
        for (const alert of alerts) {
          if (notifiedIds.current.has(alert.id)) continue
          notifiedIds.current.add(alert.id)
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification('Trade Alert', { body: alert.message })
          }
        }
      } catch (_) {}
    }

    poll()
    const interval = setInterval(poll, 10000)
    return () => clearInterval(interval)
  }, [])
}
