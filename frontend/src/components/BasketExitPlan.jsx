import { useState } from 'react'
import PnlHistoryModal from './PnlHistoryModal'

function fmtBaht(n, withSign = true) {
  if (n == null) return '—'
  const v = Number(n)
  const sign = withSign && v > 0 ? '+' : v < 0 ? '-' : ''
  return `${sign}฿${Math.abs(Math.round(v)).toLocaleString()}`
}

function fmtPct(n) {
  if (n == null) return ''
  const v = Number(n)
  const sign = v >= 0 ? '+' : ''
  return `(${sign}${v.toFixed(2)}%)`
}

const TIER_BG = {
  safe: 'border-profit/30',
  warning: 'border-warning/40',
  danger: 'border-loss/50',
}
const TIER_DOT = { safe: '🟢', warning: '🟡', danger: '🔴' }

export default function BasketExitPlan({ basket, basketWithPending }) {
  const [pnlOpen, setPnlOpen] = useState(false)
  if (!basket || basket.direction === 'flat') {
    return (
      <div className="bg-card border border-border-default rounded-lg p-4 text-text-dim text-sm h-full space-y-3">
        No open positions
        {basketWithPending && <WithPendingProjection projection={basketWithPending} />}
        {basket?.pnl_summary && (
          <PnlSummaryBox summary={basket.pnl_summary} onClick={() => setPnlOpen(true)} />
        )}
        <PnlHistoryModal open={pnlOpen} onClose={() => setPnlOpen(false)} />
      </div>
    )
  }

  const floatTone = (basket.net_float ?? 0) >= 0 ? 'text-profit' : 'text-loss'
  const dirTone = basket.direction === 'buy' ? 'text-profit' : 'text-loss'
  const meanEntry = basket.mean_entry ?? basket.avg_entry

  return (
    <div className="bg-card border border-border-default rounded-lg p-4 space-y-3 h-full">
      <div className="text-text-dim text-xs uppercase tracking-wider">Basket Exit Plan</div>
      <div className="text-sm space-y-1">
        <div>
          Net direction: <span className={`font-semibold ${dirTone}`}>
            {basket.direction.toUpperCase()}
          </span>
          <span
            className="text-text-dim cursor-help"
            title="Net lot exposure (sum buy − sum sell), total open orders"
          >
            {' '}({basket.lot_total} lot, {basket.order_count} orders)
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-4 font-mono text-text-primary">
          <span title="Volume-weighted mean of entry prices, ignores direction">
            Avg entry: {meanEntry != null ? Number(meanEntry).toFixed(2) : '—'}
          </span>
          <span>Current: {basket.current?.toFixed(2) ?? '—'}</span>
          <span title="Signed-weighted price where basket float = 0">
            Basket BE: {basket.basket_be?.toFixed(2) ?? '—'}
          </span>
          <span className={floatTone}>Net float: {fmtBaht(basket.net_float)}</span>
        </div>
      </div>
      {basketWithPending && <WithPendingProjection projection={basketWithPending} />}
      {basket.pnl_summary && (
        <PnlSummaryBox summary={basket.pnl_summary} onClick={() => setPnlOpen(true)} />
      )}
      {basket.ruin && <RuinZone ruin={basket.ruin} />}
      {basket.tp_targets.length > 0 && (
        <div>
          <div className="text-profit text-xs font-semibold uppercase tracking-wide mb-1">TP Targets (close basket)</div>
          {basket.tp_targets.map(z => (
            <div key={z.label} className="flex justify-between font-mono text-sm text-profit/90">
              <span className="w-8">{z.label}</span>
              <span>{Number(z.price).toFixed(2)}</span>
              <span className="text-right w-20">{fmtBaht(z.baht)}</span>
            </div>
          ))}
        </div>
      )}
      {basket.add_zones.length > 0 && (
        <div>
          <div className="text-loss text-xs font-semibold uppercase tracking-wide mb-1">Add Zones</div>
          {basket.add_zones.map(z => (
            <div key={z.label} className="flex justify-between font-mono text-sm text-loss/90">
              <span className="w-8">{z.label}</span>
              <span>{Number(z.price).toFixed(2)}</span>
              <span className="text-right w-20">{fmtBaht(z.baht)}</span>
            </div>
          ))}
        </div>
      )}
      {basket.cut && (
        <div className="flex justify-between font-mono text-sm text-warning border-t border-border-default pt-2">
          <span>Cut basket if {basket.cut.label} breached</span>
          <span>{Number(basket.cut.price).toFixed(2)}</span>
          <span className="text-right w-20">{fmtBaht(basket.cut.baht)}</span>
        </div>
      )}
      <PnlHistoryModal open={pnlOpen} onClose={() => setPnlOpen(false)} />
    </div>
  )
}

function WithPendingProjection({ projection }) {
  if (!projection || projection.direction === 'flat') return null
  const dirTone = projection.direction === 'buy' ? 'text-profit' : 'text-loss'
  const meanEntry = projection.mean_entry ?? projection.avg_entry
  return (
    <div
      className="bg-surface border border-warning/40 rounded p-3 text-sm space-y-1"
      title="Projection if all pending orders fill at their pending price"
    >
      <div className="text-warning text-xs font-semibold uppercase tracking-wide">
        ⏳ If all pending fill
      </div>
      <div className="text-xs">
        Direction: <span className={`font-semibold ${dirTone}`}>{projection.direction.toUpperCase()}</span>
        <span className="text-text-dim"> ({projection.lot_total} lot, {projection.order_count} orders)</span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 font-mono text-xs">
        <span>Avg entry: {meanEntry != null ? Number(meanEntry).toFixed(2) : '—'}</span>
        <span>Basket BE: {projection.basket_be?.toFixed(2) ?? '—'}</span>
      </div>
    </div>
  )
}

function PnlSummaryBox({ summary, onClick }) {
  const Cell = ({ label, row }) => {
    if (!row) return <div><div className="text-text-dim text-xs">{label}</div><div>—</div></div>
    const tone = Number(row.baht) >= 0 ? 'text-profit' : 'text-loss'
    return (
      <div>
        <div className="text-text-dim text-xs">{label}</div>
        <div className={`font-mono ${tone}`}>{fmtBaht(row.baht)}</div>
        <div className={`text-xs font-mono ${tone}`}>{fmtPct(row.pct)}</div>
      </div>
    )
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left bg-surface border border-border-default rounded p-3 grid grid-cols-3 gap-3 hover:ring-1 hover:ring-brand cursor-pointer"
    >
      <Cell label="Today" row={summary.today} />
      <Cell label="This week" row={summary.week} />
      <Cell label="This month" row={summary.month} />
    </button>
  )
}

function RuinZone({ ruin }) {
  return (
    <div className={`bg-surface border ${TIER_BG[ruin.tier] || 'border-border-default'} rounded p-3 text-sm`}>
      <div className="text-warning text-xs font-semibold uppercase tracking-wide mb-1">⚠ Ruin Zone</div>
      <div className="grid grid-cols-2 gap-x-4 font-mono">
        <span>Stop-out price:</span><span>{Number(ruin.price).toFixed(2)}</span>
        <span>Safety margin:</span>
        <span title="1 pts = $1 ในราคา · 1 pip = 0.01 ในราคา (4504.27 → 4504.28)">
          {Number(ruin.pts).toFixed(0)} pts / {(Number(ruin.pts) * 100).toFixed(0)} pips ({fmtBaht(ruin.baht_buffer)})
        </span>
        <span>Buffer:</span>
        <span>{Number(ruin.pct_buffer).toFixed(1)}% {TIER_DOT[ruin.tier] || ''}</span>
      </div>
    </div>
  )
}
