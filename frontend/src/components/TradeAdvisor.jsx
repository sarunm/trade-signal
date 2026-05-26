import BasketExitPlan from './BasketExitPlan'

export default function TradeAdvisor({ data }) {
  if (!data) return <div className="text-text-dim text-sm p-4">Loading…</div>
  return <BasketExitPlan basket={data.basket} />
}
