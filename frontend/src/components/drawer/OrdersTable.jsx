export default function OrdersTable({ title, trades, mode }) {
  return <div className="text-xs text-gray-500">{title}: {trades?.length ?? 0} ({mode})</div>
}
