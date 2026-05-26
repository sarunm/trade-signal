export default function PromotionGates({ gates, ruleId }) {
  return <div className="text-xs text-gray-500">Gates for {ruleId.slice(0, 8)}</div>
}
