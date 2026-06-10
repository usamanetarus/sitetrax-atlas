import { motion } from 'framer-motion'
import { ChartLine, Clock, FlowArrow, MapPin, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import { formatFacilityCounts, formatHeadingCounts, formatLocalDateTime } from './formatters'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

function MiniStat({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50/90 p-2 dark:border-stone-700 dark:bg-stone-900">
      <span className="flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-600 dark:text-stone-300">
        <Icon size={12} weight="duotone" />
        {label}
      </span>
      <span className="block truncate text-sm font-medium text-stone-700 dark:text-stone-200">{value || 'Unknown'}</span>
    </div>
  )
}

export default function FacilityActivityCard({ data }) {
  const facilities = formatFacilityCounts(data.by_facility)

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-stone-50 shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <ChartLine size={17} weight="duotone" />
            Facility activity
          </div>
          <Package size={20} weight="duotone" className="text-stone-500 dark:text-stone-200" />
        </div>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <div className="font-mono text-sm font-semibold text-stone-950 dark:text-stone-50">{data.container_id}</div>
            <div className="mt-1 text-sm text-stone-600 dark:text-stone-200">{data.facility || 'All facilities'}</div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold leading-none text-stone-950 dark:text-stone-50">{data.detection_count ?? 0}</div>
            <div className="text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">detections</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <MiniStat icon={Clock} label="First seen" value={formatLocalDateTime(data.first_seen)} />
          <MiniStat icon={Clock} label="Last seen" value={formatLocalDateTime(data.last_seen)} />
          <MiniStat icon={FlowArrow} label="Headings" value={formatHeadingCounts(data.headings)} />
          <MiniStat icon={MapPin} label="Facilities" value={facilities.length ? facilities.map(([name, count]) => `${name}: ${count}`).join(', ') : 'Not recorded'} />
        </div>
        {data.note && <p className="mt-3 text-xs leading-5 text-stone-500 dark:text-stone-300">{data.note}</p>}
        <CardReferences items={[cardReferences.statusCodes, cardReferences.assetHeading, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
