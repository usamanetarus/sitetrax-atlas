import { motion } from 'framer-motion'
import { ArrowRight, FlowArrow, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'

export default function InboundOutboundCard({ data }) {
  const total = data.total || 0
  const inbound = data.inbound_count || 0
  const outbound = data.outbound_count || 0
  const unknown = data.unknown_direction || 0
  const facility = data.facility || 'Unknown'
  const rangeLabel = formatDateRange(data, 'recent window')

  const inboundAssets = data.inbound_assets || []
  const outboundAssets = data.outbound_assets || []

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <FlowArrow size={17} weight="duotone" />
            Gate traffic
          </div>
          <Package size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="text-sm font-semibold text-stone-900 dark:text-stone-100">{facility}</div>
          <div className="mt-1 text-xs text-stone-500 dark:text-stone-300">{total} detections · {rangeLabel}</div>
        </div>
        <div className="mb-3 grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-center dark:border-stone-800 dark:bg-stone-950">
            <div className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">
              <ArrowRight size={12} weight="duotone" /> Inbound
            </div>
            <div className="mt-1 text-xl font-bold text-stone-800 dark:text-stone-200">{inbound}</div>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-center dark:border-stone-800 dark:bg-stone-950">
            <div className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">
              <ArrowRight size={12} weight="duotone" className="rotate-180" /> Outbound
            </div>
            <div className="mt-1 text-xl font-bold text-stone-800 dark:text-stone-200">{outbound}</div>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-center dark:border-stone-800 dark:bg-stone-950">
            <div className="text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">Unknown</div>
            <div className="mt-1 text-xl font-bold text-stone-700 dark:text-stone-200">{unknown}</div>
          </div>
        </div>
        {inboundAssets.length > 0 && (
          <div className="mb-2">
            <div className="mb-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">Inbound containers</div>
            <div className="flex flex-wrap gap-1">
              {inboundAssets.slice(0, 15).map((id, i) => (
                <span key={i} className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10px] text-stone-600 dark:bg-stone-800 dark:text-stone-200">{id}</span>
              ))}
            </div>
          </div>
        )}
        {outboundAssets.length > 0 && (
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">Outbound containers</div>
            <div className="flex flex-wrap gap-1">
              {outboundAssets.slice(0, 15).map((id, i) => (
                <span key={i} className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10px] text-stone-600 dark:bg-stone-800 dark:text-stone-200">{id}</span>
              ))}
            </div>
          </div>
        )}
        <CardReferences items={[cardReferences.assetHeading, cardReferences.facilityOverview, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
