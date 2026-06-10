import { motion } from 'framer-motion'
import { ChartLine, Clock } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'

export default function MetricsCard({ data }) {
  const byDay = data.by_day || []
  const maxCount = Math.max(...byDay.map(r => r.containers ?? r.count ?? 0), 1)
  const rangeLabel = formatDateRange(data, data.days ? `last ${data.days}d` : 'requested range')

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <ChartLine size={17} weight="duotone" />
            Metrics
          </div>
          <div className="text-right">
            <div className="text-xl font-semibold text-stone-800 dark:text-stone-200">{data.total_containers ?? 0}</div>
            <div className="text-[10px] font-semibold uppercase text-stone-600 dark:text-stone-300">total</div>
          </div>
        </div>
        <div className="mb-3 text-sm font-medium text-stone-700 dark:text-stone-200">
          {data.scope} &mdash; {rangeLabel}
        </div>
        {byDay.length > 0 && (
          <div className="space-y-1.5">
            {byDay.slice(0, 10).map((row, i) => {
              const count = row.containers ?? row.count ?? 0
              const pct = Math.round((count / maxCount) * 100)
              const label = row.date || row.facility || row.name || `Entry ${i + 1}`
              return (
                <div key={i} className="flex items-center gap-2">
                  <div className="flex w-28 shrink-0 items-center gap-1 text-[10px] text-stone-500 dark:text-stone-300">
                    <Clock size={10} weight="duotone" />
                    <span className="truncate">{label}</span>
                  </div>
                  <div className="flex-1 rounded-full bg-stone-100 dark:bg-stone-800" style={{ height: 6 }}>
                    <div className="h-full rounded-full bg-stone-500 dark:bg-stone-300 transition-all" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-8 shrink-0 text-right text-[10px] font-semibold text-stone-600 dark:text-stone-200">{count}</span>
                </div>
              )
            })}
          </div>
        )}
        <CardReferences items={[cardReferences.facilityMetrics, cardReferences.facilityOverview]} />
      </motion.div>
    </SpotlightShell>
  )
}
