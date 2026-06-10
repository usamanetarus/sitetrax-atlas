import { motion } from 'framer-motion'
import { Lightbulb, Sparkle } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
export default function OpportunityCard({ data }) {
  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <Lightbulb size={17} weight="duotone" />
            Opportunity logged
          </div>
          <Sparkle size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-1.5 text-sm font-semibold text-stone-900 dark:text-stone-100">{data.category || 'New capability'}</div>
        <p className="text-sm leading-relaxed text-stone-600 dark:text-stone-200">{data.message}</p>
        <CardReferences items={[cardReferences.support, cardReferences.monitoringRules]} />
      </motion.div>
    </SpotlightShell>
  )
}
