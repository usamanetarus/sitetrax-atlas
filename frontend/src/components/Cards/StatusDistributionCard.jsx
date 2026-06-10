import { motion } from 'framer-motion'
import { ShieldCheck, Warning } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function StatusDistributionCard({ data }) {
  const byStatus = data.by_status || {}
  const total = data.total || 0
  const facility = data.facility || 'All facilities'

  const statuses = Object.entries(byStatus).sort((a, b) => b[1] - a[1])

  const getStatusColor = (code) => {
    return 'bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-200'
  }

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <ShieldCheck size={17} weight="duotone" />
            Status breakdown
          </div>
          <ShieldCheck size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="text-sm font-semibold text-stone-900 dark:text-stone-100">{facility}</div>
          <div className="mt-1 text-xs text-stone-500 dark:text-stone-300">{total} detections</div>
        </div>
        <div className="flex flex-col gap-2">
          {statuses.map(([code, count]) => {
            const pct = total > 0 ? Math.round((count / total) * 100) : 0
            return (
              <div key={code} className="flex items-center gap-2">
                <span className={`inline-flex w-8 shrink-0 justify-center rounded px-1.5 py-0.5 text-[10px] font-bold ${getStatusColor(code)}`}>{code}</span>
                <div className="flex-1">
                  <div className="h-2 overflow-hidden rounded-full bg-stone-100 dark:bg-stone-800">
                    <div className="h-full rounded-full bg-stone-500 dark:bg-stone-300" style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <span className="w-12 text-right text-xs font-medium text-stone-600 dark:text-stone-200">{count}</span>
                <span className="w-8 text-right text-xs text-stone-400 dark:text-stone-400">{pct}%</span>
              </div>
            )
          })}
        </div>
        {byStatus.A0 < total * 0.8 && total > 10 && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-stone-50 p-2 dark:bg-stone-950">
            <Warning size={16} weight="duotone" className="shrink-0 text-stone-400" />
            <span className="text-xs text-stone-600 dark:text-stone-300">Low confidence rate is {Math.round(((total - (byStatus.A0 || 0)) / total) * 100)}% — consider reviewing camera positioning.</span>
          </div>
        )}
        <CardReferences items={[cardReferences.statusCodes, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
