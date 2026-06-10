import { motion } from 'framer-motion'
import { BellRinging, Clock, ShieldCheck, Warning, Siren } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'

export default function RuleHistoryCard({ data }) {
  const alerts = data.alerts || []
  const count = data.count || 0
  const rangeLabel = formatDateRange(data, 'requested range')

  const getTemplateIcon = (template) => {
    if (template === 'container_arrival') return <BellRinging size={14} weight="duotone" />
    if (template === 'dwell_time') return <Clock size={14} weight="duotone" />
    if (template === 'status_change') return <ShieldCheck size={14} weight="duotone" />
    if (template === 'facility_departure') return <Warning size={14} weight="duotone" />
    if (template === 'low_confidence') return <Siren size={14} weight="duotone" />
    if (template === 'review_queue') return <BellRinging size={14} weight="duotone" />
    if (template === 'camera_offline') return <Warning size={14} weight="duotone" />
    return <BellRinging size={14} weight="duotone" />
  }

  const getTemplateColor = (template) => {
    if (template === 'low_confidence') return 'bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300'
    return 'bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-200'
  }

  const getTemplateLabel = (template) => {
    if (template === 'container_arrival') return 'Arrival'
    if (template === 'dwell_time') return 'Dwell'
    if (template === 'status_change') return 'Status'
    if (template === 'facility_departure') return 'Departure'
    if (template === 'low_confidence') return 'Low Confidence'
    if (template === 'review_queue') return 'Review Queue'
    if (template === 'camera_offline') return 'Camera Offline'
    return template
  }

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
            <BellRinging size={17} weight="duotone" />
            Alert history
          </div>
          <Siren size={20} weight="duotone" className="text-stone-500 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{count} alerts fired · {rangeLabel}</div>
        </div>
        {alerts.length === 0 ? (
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-4 text-center dark:border-stone-800 dark:bg-stone-950">
            <BellRinging size={24} weight="duotone" className="mx-auto mb-2 text-stone-300 dark:text-stone-600" />
            <div className="text-sm text-stone-500 dark:text-stone-300">No alerts fired in this window</div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {alerts.slice(0, 20).map((alert, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-stone-200 bg-stone-50/80 p-2 dark:border-stone-800 dark:bg-stone-950">
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${getTemplateColor(alert.template)}`}>
                  {getTemplateIcon(alert.template)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-stone-800 dark:text-stone-200">{alert.display_name || getTemplateLabel(alert.template)}</span>
                    <span className="text-[10px] text-stone-400 dark:text-stone-400">{alert.rule_id}</span>
                  </div>
                  {alert.trigger_description && (
                    <div className="mt-0.5 text-[10px] leading-4 text-stone-400 dark:text-stone-400">{alert.trigger_description}</div>
                  )}
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {Object.entries(alert.params || {}).map(([k, v]) => (
                      <span key={k} className="inline-flex rounded bg-stone-100 px-1.5 py-0.5 text-[10px] text-stone-500 dark:bg-stone-800 dark:text-stone-300">
                        {k}: {String(v)}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="shrink-0 text-[10px] text-stone-400 dark:text-stone-400">
                  {alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                </div>
              </div>
            ))}
          </div>
        )}
        <CardReferences items={[cardReferences.monitoringRules, cardReferences.statusCodes]} />
      </motion.div>
    </SpotlightShell>
  )
}
