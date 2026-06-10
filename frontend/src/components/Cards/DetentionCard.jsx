import { motion } from 'framer-motion'
import { Clock, Warning, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function DetentionCard({ data }) {
  const containers = data.containers || []
  const facility = data.facility || 'Unknown'
  const threshold = data.threshold_hours || 72

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-red-950/15 dark:bg-red-500">
            <Warning size={17} weight="duotone" />
            Detention risk
          </div>
          <Package size={20} weight="duotone" className="text-red-500 dark:text-red-300" />
        </div>
        <div className="mb-3">
          <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{facility}</div>
          <div className="mt-1 text-xs text-stone-500 dark:text-stone-300">{containers.length} containers over {threshold}h · sorted by dwell time</div>
        </div>
        <div className="flex flex-col gap-2">
          {containers.slice(0, 10).map((c, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border border-stone-200 bg-stone-50/90 p-2 dark:border-stone-800 dark:bg-stone-950">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-300">
                <span className="text-[10px] font-bold">#{i + 1}</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-mono text-sm font-semibold text-stone-950 dark:text-stone-50">{c.container_id}</div>
                <div className="mt-0.5 flex items-center gap-2 text-xs text-stone-500 dark:text-stone-300">
                  <Clock size={12} weight="duotone" />
                  <span>{c.dwell_hours}h dwell · status {c.status_code}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
        <CardReferences items={[cardReferences.detention, cardReferences.assetHeading, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
