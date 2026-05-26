export default function ShadowsList({ shadows }) {
  return <div className="text-xs text-gray-500">Shadows ({shadows?.shadows?.length ?? 0})</div>
}
