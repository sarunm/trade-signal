import { useState } from 'react'
import TrustTierBadge from './TrustTierBadge'
import PaperRuleDrawer from './PaperRuleDrawer'

const ALIVE_DOT = {
  active: 'bg-emerald-500',
  near: 'bg-amber-400',
  far: 'bg-gray-500',
  idle: 'bg-gray-700',
}

function ageChip(seconds) {
  if (!seconds || seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

function aliveTone(rule) {
  const last = rule.last_activity_at ? new Date(rule.last_activity_at).getTime() : 0
  const ageMs = last ? Date.now() - last : Infinity
  if (rule.last_signal_status === 'active') return 'active'
  if (rule.last_signal_status === 'near') return 'near'
  if (ageMs > 30 * 60 * 1000) return 'idle'
  return rule.last_signal_status || 'idle'
}

function formatBaht(n) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `${sign}฿${Math.round(v).toLocaleString()}`
}

export default function PaperRuleCard({ rule, pattern }) {
  const [open, setOpen] = useState(false)
  const tone = aliveTone(rule)
  const dot = ALIVE_DOT[tone] || ALIVE_DOT.idle

  const start = Number(rule.virtual_balance_start ?? 0)
  const cumPnl = Number(rule.cum_pnl_realized ?? 0)
  const current = start + cumPnl
  const cumPct = start > 0 ? (cumPnl / start) * 100 : 0
  const balanceTone = current < start ? 'text-red-400' : 'text-gray-100'
  const pnlTone = cumPnl > 0 ? 'text-emerald-400' : cumPnl < 0 ? 'text-red-400' : 'text-gray-300'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded p-3 space-y-2">
      <button
        type="button"
        className="w-full flex items-center justify-between hover:bg-gray-800/50 -m-3 p-3 rounded-t transition-colors"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? 'Collapse rule details' : 'Expand rule details'}
      >
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-sm font-medium">{rule.mode}</span>
          <span className="text-xs text-gray-400">[{ageChip(rule.age_seconds)}]</span>
        </div>
        <div className="flex items-center gap-2">
          <TrustTierBadge tier={rule.trust_tier} />
          <span className="inline-flex items-center justify-center w-7 h-7 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-base leading-none">
            {open ? '▴' : '▾'}
          </span>
        </div>
      </button>
      <div className="text-xs text-gray-400 text-left">
        {pattern?.indicator_slugs?.join(' + ') || '—'}
      </div>
      <div className="flex justify-between text-xs">
        <div>Open: <span className="text-gray-100">{rule.open_trades_count ?? 0}</span></div>
        <div>
          Balance: <span className={balanceTone}>฿{Math.round(current).toLocaleString()}</span>
          <span className="text-gray-500"> / ฿{Math.round(start).toLocaleString()}</span>
        </div>
      </div>
      <div className="text-xs">
        Cum PnL: <span className={pnlTone}>{formatBaht(cumPnl)}</span>
        <span className={`ml-1 ${pnlTone}`}>({cumPct >= 0 ? '+' : ''}{cumPct.toFixed(1)}%)</span>
      </div>
      {open && <PaperRuleDrawer rule={rule} pattern={pattern} />}
    </div>
  )
}
