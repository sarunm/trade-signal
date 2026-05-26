export default function SignalTrail({ signals }) {
  return <div className="text-xs text-gray-500">Signal trail ({signals?.length ?? 0})</div>
}
