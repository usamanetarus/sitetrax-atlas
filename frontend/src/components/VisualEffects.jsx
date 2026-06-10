export function AppBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden bg-stone-50 dark:bg-stone-950">
      <div className="absolute inset-0 bg-[linear-gradient(to_bottom,rgba(255,255,255,0.18),transparent_18%),linear-gradient(to_right,rgba(0,0,0,0.02)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.02)_1px,transparent_1px)] bg-[size:auto,24px_24px,24px_24px] opacity-40 dark:bg-[linear-gradient(to_bottom,rgba(255,255,255,0.01),transparent_20%),linear-gradient(to_right,rgba(255,255,255,0.01)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.01)_1px,transparent_1px)] dark:opacity-15" />
    </div>
  )
}

export function SpotlightShell({ children, className = '' }) {
  return (
    <div className={`relative overflow-hidden ${className}`}>
      {children}
    </div>
  )
}
