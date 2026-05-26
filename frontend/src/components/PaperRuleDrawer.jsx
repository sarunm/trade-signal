import { usePaperRuleDetail } from '../hooks/usePaperSignals'
import SignalTrail from './drawer/SignalTrail'
import OrdersTable from './drawer/OrdersTable'
import PatternConditions from './drawer/PatternConditions'
import PromotionGates from './drawer/PromotionGates'
import ShadowsList from './drawer/ShadowsList'

export default function PaperRuleDrawer({ rule, pattern }) {
  const { data, error, loading, refetch } = usePaperRuleDetail(rule.id, rule.pattern_id)
  const trades = data.trades || []
  const active = trades.filter((t) => t.status === 'open')
  const closed = trades.filter((t) => t.status === 'closed')

  return (
    <div className="border-t border-gray-800 pt-3 mt-2 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">Drawer</span>
        <button
          type="button"
          onClick={refetch}
          disabled={loading}
          className="text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-50"
        >
          {loading ? '⟳ refreshing…' : '⟳ refresh'}
        </button>
      </div>
      {error && <div className="text-xs text-red-400">Failed to load: {String(error)}</div>}

      <SignalTrail signals={data.signals} />
      <OrdersTable title={`Active Orders (${active.length})`} trades={active} mode="active" />
      <OrdersTable title="Recent History" trades={closed} mode="history" />
      <PatternConditions rule={rule} pattern={pattern} />
      <PromotionGates gates={data.gates} ruleId={rule.id} />
      <ShadowsList shadows={data.shadows} />
    </div>
  )
}
