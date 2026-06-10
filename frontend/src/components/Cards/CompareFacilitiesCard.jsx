import { motion } from 'framer-motion'
import { FlowArrow, ChartLine, ArrowRight, ArrowLeft, Package, Star } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'

export default function CompareFacilitiesCard({ data }) {
  const fa = data.facility_a || {}
  const fb = data.facility_b || {}
  const winner = data.busier_facility || 'N/A'
  const rangeLabel = formatDateRange(data, 'requested range')

  const StatBox = ({ label, a, b, highlight = false }) => (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 dark:border-stone-700 dark:bg-stone-900">
      <div className="mb-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">{label}</div>
      <div className="grid grid-cols-2 gap-2">
        <div className={`text-center ${highlight && a >= b ? 'text-stone-700 dark:text-stone-200' : ''}`}>
          <div className="text-sm font-bold">{a}</div>
          <div className="text-[10px] text-stone-400">{fa.facility}</div>
        </div>
        <div className={`text-center ${highlight && b > a ? 'text-stone-700 dark:text-stone-200' : ''}`}>
          <div className="text-sm font-bold">{b}</div>
          <div className="text-[10px] text-stone-400">{fb.facility}</div>
        </div>
      </div>
    </div>
  )

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <FlowArrow size={17} weight="duotone" />
            Facility comparison
          </div>
          <ChartLine size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-3 flex items-center justify-between">
          <div className="text-center">
            <div className="text-sm font-semibold text-stone-900 dark:text-stone-100">{fa.facility}</div>
          </div>
          <div className="text-xs text-stone-400">vs</div>
          <div className="text-center">
            <div className="text-sm font-semibold text-stone-900 dark:text-stone-100">{fb.facility}</div>
          </div>
        </div>
        <div className="mb-3 flex items-center justify-center gap-2 rounded-lg bg-stone-50 p-2 dark:bg-stone-950">
          <Star size={16} weight="duotone" className="text-stone-400" />
          <span className="text-sm font-semibold text-stone-800 dark:text-stone-200">Busier: {winner} ({data.busier_scan_count} scans)</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StatBox label="Total scans" a={fa.total_scans} b={fb.total_scans} highlight />
          <StatBox label="A0 rate" a={`${fa.a0_rate_percent}%`} b={`${fb.a0_rate_percent}%`} highlight />
          <StatBox label="Inbound" a={fa.inbound} b={fb.inbound} />
          <StatBox label="Outbound" a={fa.outbound} b={fb.outbound} />
        </div>
        <div className="mt-3 text-xs text-stone-400 dark:text-stone-400">Comparison over {rangeLabel}</div>
        <CardReferences items={[cardReferences.facilityOverview, cardReferences.statusCodes, cardReferences.assetHeading]} />
      </motion.div>
    </SpotlightShell>
  )
}
