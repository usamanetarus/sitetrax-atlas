import { motion } from 'framer-motion'
import { Buildings, ChartLine, Clock, MapPin, VideoCamera, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'

export default function OverviewCard({ data }) {
  const facility = data.facility || 'Unknown'
  const rangeLabel = formatDateRange(data, 'requested range')
  const summary = data.summary || {}
  const metrics = data.metrics || []
  const recent = data.recent_activity || []
  const last = data.last_scan || null

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900"
      >
        <div className="mb-3 flex items-center gap-2">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-stone-50 shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <Buildings size={15} weight="duotone" />
            Facility Overview
          </div>
          <span className="text-xs text-stone-400 dark:text-stone-400">{rangeLabel}</span>
        </div>

        <div className="mb-3 font-mono text-sm font-semibold text-stone-950 dark:text-stone-50">{facility}</div>

        {/* Summary stats */}
        <div className="mb-3 grid grid-cols-2 gap-2">
          <StatTile icon={Package} label="Total Scans" value={summary.total_scans || 0} />
          <StatTile icon={Clock} label="Recent" value={summary.recent_scans || 0} />
        </div>

        {/* Last scan */}
        {last && (
          <div className="mb-3 rounded-lg border border-stone-200 bg-stone-50/80 p-2.5 dark:border-stone-800 dark:bg-stone-950">
            <div className="mb-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-400">Last Scan</div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-semibold text-stone-900 dark:text-stone-200">{last.text || last.container_id || 'Unknown'}</span>
              <span className={`rounded px-1 py-0 text-[9px] font-medium ${
                (last.status_code || 'A0') === 'A0'
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                  : 'bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-200'
              }`}>{last.status_code || 'A0'}</span>
            </div>
            {last.datetime && (
              <div className="mt-0.5 text-[10px] text-stone-400 dark:text-stone-400">{formatTime(last.datetime)}</div>
            )}
          </div>
        )}

        {/* Recent activity */}
        {recent.length > 0 && (
          <div className="mb-2">
            <div className="mb-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-400">Recent Activity</div>
            <div className="space-y-1.5">
              {recent.slice(0, 5).map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex items-center justify-between rounded-md border border-stone-200/70 bg-stone-50/70 px-2 py-1.5 dark:border-stone-800 dark:bg-stone-950"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-semibold text-stone-800 dark:text-stone-200">{item.text || item.container_id || '?'}</span>
                    <span className={`rounded px-1 py-0 text-[9px] font-medium ${
                      (item.status_code || 'A0') === 'A0'
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300'
                    }`}>
                      {item.status_code || 'A0'}
                    </span>
                  </div>
                  <span className="text-[10px] text-stone-400 dark:text-stone-400">{formatTime(item.datetime)}</span>
                </motion.div>
              ))}
            </div>
          </div>
        )}
      </motion.div>
    </SpotlightShell>
  )
}

function StatTile({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50/80 p-2.5 dark:border-stone-800 dark:bg-stone-950">
      <div className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase text-stone-500 dark:text-stone-400">
        <Icon size={12} weight="duotone" />
        {label}
      </div>
      <div className="text-lg font-semibold leading-none text-stone-950 dark:text-stone-50">{value}</div>
      <CardReferences items={[cardReferences.statusCodes, cardReferences.assetHeading, cardReferences.facilityOverview, cardReferences.operationalInterpretation]} />
    </div>
  )
}

function formatTime(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}
