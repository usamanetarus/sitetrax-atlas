import { motion } from 'framer-motion'
import { Truck, MapPin, Clock, ArrowRight, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import { formatLocalDateTime } from './formatters'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function AssetJourneyCard({ data }) {
  const journey = data.journey || []
  const containerId = data.container_id || 'Unknown'
  const facilityCount = data.facility_count || 0
  const totalDetections = data.total_detections || 0

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <Truck size={17} weight="duotone" />
            Container journey
          </div>
          <Package size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="font-mono text-sm font-semibold text-stone-900 dark:text-stone-100">{containerId}</div>
          <div className="mt-1 text-xs text-stone-500 dark:text-stone-300">{totalDetections} detections · {facilityCount} {facilityCount === 1 ? 'facility' : 'facilities'}</div>
        </div>
        <div className="relative flex flex-col gap-3">
          {journey.map((stop, i) => (
            <div key={i} className="relative flex gap-3">
              <div className="flex flex-col items-center">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-stone-200 text-[10px] font-bold text-stone-700 dark:bg-stone-800 dark:text-stone-200">
                  {i + 1}
                </div>
                {i < journey.length - 1 && (
                  <div className="mt-1 h-full w-px bg-stone-200 dark:bg-stone-800" />
                )}
              </div>
              <div className="min-w-0 flex-1 rounded-lg border border-stone-200 bg-stone-50 p-2 dark:border-stone-800 dark:bg-stone-950">
                <div className="flex items-center gap-1.5 text-sm font-semibold text-stone-900 dark:text-stone-100">
                  <MapPin size={14} weight="duotone" className="shrink-0 text-stone-400 dark:text-stone-200" />
                  {stop.facility}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-stone-500 dark:text-stone-300">
                  <span className="inline-flex items-center gap-1">
                    <Clock size={12} weight="duotone" />
                    {formatLocalDateTime(stop.datetime)}
                  </span>
                  {stop.heading && stop.heading !== '-' && (
                    <span className="inline-flex items-center gap-1">
                      <ArrowRight size={12} weight="duotone" className={stop.heading === 'R2L' ? 'rotate-180' : ''} />
                      {stop.heading}
                    </span>
                  )}
                  <span className="inline-flex rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-200">
                    {stop.status_code}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
        <CardReferences items={[cardReferences.assetHeading, cardReferences.facilityOverview, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
