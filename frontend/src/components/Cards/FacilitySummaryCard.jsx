import { motion } from 'framer-motion'
import { Warehouse, ChartLine, Clock, ArrowRight, ArrowLeft, Warning, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import { formatLocalDateTime } from './formatters'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function FacilitySummaryCard({ data }) {
  const summary = data.summary || {}
  const facility = data.facility || 'Unknown'
  const statusDistribution = data.status_distribution || {}
  const detentionRisks = data.top_detention_risks || []

  const total7d = summary.total_containers_7d || 0
  const total24h = summary.total_scans_24h || 0
  const a0Rate = summary.a0_rate_percent || 0
  const inbound = summary.inbound_24h || 0
  const outbound = summary.outbound_24h || 0
  const detentionCount = summary.detention_risk_count || 0

  const statuses = Object.entries(statusDistribution).sort((a, b) => b[1] - a[1])

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-stone-50 shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <Warehouse size={17} weight="duotone" />
            Facility summary
          </div>
          <ChartLine size={20} weight="duotone" className="text-stone-500 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{facility}</div>
          {summary.latest_scan_time && (
            <div className="mt-1 flex items-center gap-1 text-xs text-stone-500 dark:text-stone-300">
              <Clock size={12} weight="duotone" />
              Last scan: {summary.latest_scan} at {formatLocalDateTime(summary.latest_scan_time)}
            </div>
          )}
        </div>
        <div className="mb-3 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-center dark:border-stone-800 dark:bg-stone-950">
            <div className="text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">7-day total</div>
            <div className="mt-1 text-xl font-bold text-stone-950 dark:text-stone-50">{total7d}</div>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-center dark:border-stone-800 dark:bg-stone-950">
            <div className="text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">24h scans</div>
            <div className="mt-1 text-xl font-bold text-stone-950 dark:text-stone-50">{total24h}</div>
          </div>
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-2 text-center dark:border-emerald-900/30 dark:bg-emerald-950/20">
            <div className="text-[10px] font-semibold uppercase text-emerald-600 dark:text-emerald-400">A0 rate</div>
            <div className="mt-1 text-xl font-bold text-emerald-800 dark:text-emerald-200">{a0Rate}%</div>
          </div>
          <div className={`rounded-lg border p-2 text-center ${detentionCount > 0 ? 'border-red-200 bg-red-50 dark:border-red-900/30 dark:bg-red-950/20' : 'border-stone-200 bg-stone-50 dark:border-stone-800 dark:bg-stone-950'}`}>
            <div className={`text-[10px] font-semibold uppercase ${detentionCount > 0 ? 'text-red-600 dark:text-red-400' : 'text-stone-500 dark:text-stone-300'}`}>Detention risk</div>
            <div className={`mt-1 text-xl font-bold ${detentionCount > 0 ? 'text-red-800 dark:text-red-200' : 'text-stone-950 dark:text-stone-50'}`}>{detentionCount}</div>
          </div>
        </div>
        <div className="mb-3 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-center dark:border-stone-800 dark:bg-stone-950">
            <div className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-600 dark:text-stone-300">
              <ArrowRight size={12} weight="duotone" /> Inbound
            </div>
            <div className="mt-1 text-lg font-bold text-stone-950 dark:text-stone-50">{inbound}</div>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-center dark:border-stone-800 dark:bg-stone-950">
            <div className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-600 dark:text-stone-300">
              <ArrowLeft size={12} weight="duotone" /> Outbound
            </div>
            <div className="mt-1 text-lg font-bold text-stone-950 dark:text-stone-50">{outbound}</div>
          </div>
        </div>
        {statuses.length > 0 && (
          <div className="mb-3">
            <div className="mb-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-300">Status breakdown</div>
            <div className="flex flex-wrap gap-1">
              {statuses.map(([code, count]) => (
                <span key={code} className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${code === 'A0' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300' : 'bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-200'}`}>
                  {code}: {count}
                </span>
              ))}
            </div>
          </div>
        )}
        {detentionRisks.length > 0 && (
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase text-red-500 dark:text-red-400">Top detention risks</div>
            <div className="flex flex-col gap-1">
              {detentionRisks.map((r, i) => (
                <div key={i} className="flex items-center gap-2 rounded border border-red-100 bg-red-50/50 px-2 py-1 dark:border-red-900/20 dark:bg-red-950/10">
                  <Warning size={12} weight="duotone" className="shrink-0 text-red-500 dark:text-red-400" />
                  <span className="font-mono text-xs text-stone-800 dark:text-stone-200">{r.container_id}</span>
                  <span className="ml-auto text-xs text-red-600 dark:text-red-300">{r.dwell_hours}h</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <CardReferences items={[cardReferences.statusCodes, cardReferences.assetHeading, cardReferences.facilityOverview, cardReferences.detention]} />
      </motion.div>
    </SpotlightShell>
  )
}
