export default function SectionDivider({ label }) {
  return (
    <div className="flex items-center gap-3 my-6">
      <div className="h-px flex-1 bg-border-default" />
      <span className="text-xs font-semibold uppercase tracking-wider text-text-dim">
        {label}
      </span>
      <div className="h-px flex-1 bg-border-default" />
    </div>
  )
}
