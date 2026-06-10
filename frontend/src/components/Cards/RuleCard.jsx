import { motion } from 'framer-motion'
import { BellRinging, CheckCircle, FlowArrow } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
export default function RuleCard({ data }) {
  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <CheckCircle size={17} weight="duotone" />
            Rule created
          </div>
          <BellRinging size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-stone-900 dark:text-stone-100">
          <FlowArrow size={17} weight="duotone" className="text-stone-400" />
          {data.template || 'Monitoring Rule'}
        </div>
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(data.params || {}).map(([k, v]) => (
            <div key={k} className="rounded-lg border border-stone-200 bg-stone-50/80 p-2 dark:border-stone-800 dark:bg-stone-950">
              <span className="block text-[10px] font-semibold uppercase text-stone-400 dark:text-stone-400">{k.replace(/_/g, ' ')}</span>
              <span className="block truncate font-mono text-sm font-medium text-stone-700 dark:text-stone-200">{String(v)}</span>
            </div>
          ))}
        </div>
        <CardReferences items={[cardReferences.monitoringRules, cardReferences.support]} />
      </motion.div>
    </SpotlightShell>
  )
}
