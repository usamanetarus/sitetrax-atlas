import { motion } from 'framer-motion'
import { Clock, MapPin, Siren, Warning } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function AlertCard({ data }) {
  const ts = new Date(data.event?.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-red-950/15 dark:bg-red-500">
            <Warning size={17} weight="duotone" />
            Alert triggered
          </div>
          <Siren size={21} weight="duotone" className="text-red-500 dark:text-red-300" />
        </div>
        <div className="mb-3 text-sm font-semibold text-stone-950 dark:text-stone-50">Container event matched a rule</div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-stone-200 bg-stone-50/90 p-2 dark:border-stone-800 dark:bg-stone-950">
            <span className="block text-[10px] font-semibold uppercase text-red-500 dark:text-red-300">Container</span>
            <span className="block truncate font-mono text-sm font-medium text-stone-700 dark:text-stone-200">{data.event?.container_id}</span>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50/90 p-2 dark:border-stone-800 dark:bg-stone-950">
            <span className="flex items-center gap-1 text-[10px] font-semibold uppercase text-red-500 dark:text-red-300"><MapPin size={12} weight="duotone" />Location</span>
            <span className="block truncate text-sm font-medium text-stone-700 dark:text-stone-200">{data.event?.location}</span>
          </div>
          <div className="rounded-lg border border-stone-200 bg-stone-50/90 p-2 dark:border-stone-800 dark:bg-stone-950">
            <span className="flex items-center gap-1 text-[10px] font-semibold uppercase text-red-500 dark:text-red-300"><Clock size={12} weight="duotone" />Time</span>
            <span className="text-sm font-medium text-stone-700 dark:text-stone-200">{ts}</span>
          </div>
          {data.alerts?.[0]?.trigger && (
            <div className="col-span-2 rounded-lg border border-red-200 bg-red-50/70 p-2 dark:border-red-900/40 dark:bg-red-950/20">
              <span className="text-xs leading-5 text-red-600 dark:text-red-300">{data.alerts[0].trigger}</span>
            </div>
          )}
        </div>
        <CardReferences items={[cardReferences.statusCodes, cardReferences.monitoringRules]} />
      </motion.div>
    </SpotlightShell>
  )
}
