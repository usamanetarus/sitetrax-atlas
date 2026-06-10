import { motion } from 'framer-motion'
import { Clock, MapPin, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import { formatLocalDateTime } from './formatters'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

function Detail({ label, value, mono = false }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 dark:border-stone-700 dark:bg-stone-900">
      <span className="block text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">{label}</span>
      <span className={`block truncate text-sm font-medium text-stone-700 dark:text-stone-200 ${mono ? 'font-mono' : ''}`}>{value || 'Unknown'}</span>
    </div>
  )
}

export default function LastSeenCard({ data }) {
  return (
    <SpotlightShell className="rounded-xl">
      <motion.div
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-stone-50 shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <MapPin size={17} weight="duotone" />
            Last seen
          </div>
          <Package size={20} weight="duotone" className="text-stone-500 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="font-mono text-sm font-semibold text-stone-950 dark:text-stone-50">{data.container_id}</div>
          <div className="mt-1 flex items-center gap-1.5 text-sm text-stone-500 dark:text-stone-300">
            <Clock size={14} weight="duotone" />
            {data.last_seen_ago || formatLocalDateTime(data.last_seen_time)}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Detail label="Location" value={data.last_seen_location} />
          <Detail label="Time" value={formatLocalDateTime(data.last_seen_time)} />
          <Detail label="Status" value={data.status_code} mono />
          <Detail label="Heading" value={data.heading} mono />
          <Detail label="Record total" value={data.total_detections_on_record} />
        </div>
        <CardReferences items={[cardReferences.statusCodes, cardReferences.assetHeading, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
