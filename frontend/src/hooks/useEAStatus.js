import { useCallback, useEffect, useState } from 'react'

const API = 'http://localhost:8000'
const POLL_MS = 10_000

export function useEAStatus(accountId) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)

  const fetchStatus = useCallback(async () => {
    if (!accountId) {
      setStatus(null)
      return
    }
    try {
      const res = await fetch(`${API}/api/ea-status?account_id=${accountId}`)
      if (res.status === 404) {
        setStatus({ connected: false, seconds_since_last_seen: null, never_seen: true })
        setError(null)
        return
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const body = await res.json()
      setStatus(body)
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [accountId])

  useEffect(() => {
    fetchStatus()
    const id = setInterval(fetchStatus, POLL_MS)
    return () => clearInterval(id)
  }, [fetchStatus])

  return { status, error }
}
