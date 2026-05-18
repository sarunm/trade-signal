import { useState, useEffect, useCallback } from 'react'

export function usePolling(fetcher, intervalMs = 30000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [tick, setTick] = useState(0)

  const refetch = useCallback(() => setTick(t => t + 1), [])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const result = await fetcher()
        if (!cancelled) {
          setData(result)
          setLastUpdated(new Date())
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e)
      }
    }
    run()
    const id = setInterval(run, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [fetcher, intervalMs, tick])

  return { data, error, lastUpdated, refetch }
}
