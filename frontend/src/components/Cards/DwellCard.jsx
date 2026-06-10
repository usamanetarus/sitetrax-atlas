import { motion } from 'framer-motion'
import { Clock, MapPin, Package, Timer } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import { formatLocalDateTime } from './formatters'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

function formatGap(hours) {
  if (!Number.isFinite(Number(hours))) return null
  const value = Number(hours)
  if (value >= 24) return `${(value / 24).toFixed(1)} days`
  return `${value.toFixed(1)} hours`
}

export default function DwellCard({ data }) {
  const gap = formatGap(data.gap_between_two_most_recent_detections_hours)

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <Timer size={17} weight="duotone" />
            Dwell estimate
          </div>
          <Package size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-4">
          <div className="font-mono text-sm font-semibold text-stone-900 dark:text-stone-100">{data.container_id}</div>
          <div className="mt-2 text-3xl font-semibold leading-none text-stone-800 dark:text-stone-200">{data.time_since_last_seen || 'Unknown'}</div>
          <div className="mt-1 text-xs font-semibold uppercase text-stone-500 dark:text-stone-300">since last detection</div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-stone-200 bg-stone-50/80 p-2 dark:border-stone-800 dark:bg-stone-950">
            <span className="flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300"><MapPin size={12} weight="duotone" />Facility</span>
            <span className="block truncate text-sm font-medium text-stone-700 dark:text-stone-200">{data.facility || 'Unknown'}</span>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50/80 p-2 dark:border-stone-800 dark:bg-stone-950">
            <span className="flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300"><Clock size={12} weight="duotone" />Last seen</span>
            <span className="block truncate text-sm font-medium text-stone-700 dark:text-stone-200">{formatLocalDateTime(data.last_seen)}</span>
          </div>
          {gap && (
            <div className="col-span-2 rounded-lg border border-stone-200 bg-stone-50/80 p-2 dark:border-stone-800 dark:bg-stone-950">
              <span className="block text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">Gap between two most recent detections</span>
              <span className="block text-sm font-medium text-stone-700 dark:text-stone-200">{gap}</span>
            </div>
          )}
        </div>
        {data.note && <p className="mt-3 text-xs leading-5 text-stone-500 dark:text-stone-300">{data.note}</p>}
        <CardReferences items={[cardReferences.detention, cardReferences.assetHeading, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
