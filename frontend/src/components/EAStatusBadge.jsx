import React from 'react'
import { useEAStatus } from '../hooks/useEAStatus'

function formatGap(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h`
}

export default function EAStatusBadge({ accountId }) {
  const { status } = useEAStatus(accountId)

  if (!status) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-500">
        EA: …
      </span>
    )
  }

  if (status.never_seen) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400">
        🔴 EA: never seen
      </span>
    )
  }

  const gap = formatGap(status.seconds_since_last_seen)
  if (status.connected) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-green-900/40 text-green-300">
        🟢 EA connected ({gap} ago)
      </span>
    )
  }
  return (
    <span className="text-xs px-2 py-1 rounded bg-red-900/40 text-red-300 animate-pulse">
      🔴 EA disconnected ({gap})
    </span>
  )
}
