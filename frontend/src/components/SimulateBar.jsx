import { motion, AnimatePresence } from 'framer-motion'
import { Timer, Truck } from './Icons'

function formatTemplateLabel(template) {
  return String(template || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function getRuleIcon(template) {
  if (template === 'dwell_time') return Timer
  if (template === 'status_change') return Truck
  if (template === 'facility_departure') return Truck
  if (template === 'low_confidence') return Timer
  if (template === 'review_queue') return Timer
  if (template === 'camera_offline') return Truck
  return Truck
}

export default function SimulateBar({ rules, simulating, onSimulate }) {
  return (
    <AnimatePresence>
      {rules.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
          transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
          className="shrink-0 border-t border-stone-200/70 bg-white/65 px-4 py-2.5 backdrop-blur-xl dark:border-stone-800 dark:bg-stone-950 sm:px-6">
          <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-2">
            <span className="mr-1 text-[10px] font-semibold uppercase text-stone-400 dark:text-stone-400">Simulate</span>
            {rules.slice(0, 4).map((rule) => {
              const Icon = getRuleIcon(rule.template)
              const label = rule.display_name || formatTemplateLabel(rule.template)
              return (
                <motion.button key={rule.id} onClick={() => onSimulate(rule)} disabled={simulating}
                  whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                  className={`inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white px-2.5 py-1 text-xs font-medium text-stone-600 shadow-sm transition-all hover:border-stone-300 hover:text-stone-900 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:hover:border-stone-700 dark:hover:text-stone-100 ${simulating ? 'pointer-events-none opacity-40' : ''}`}>
                  <Icon size={14} weight="duotone" className="text-stone-500 dark:text-stone-200" />
                  <span className="font-mono text-[10px]">{rule.params.container_id ? rule.params.container_id.substring(0, 11) : 'any'}</span>
                  <span className="text-stone-300 dark:text-stone-600">@</span>
                  <span className="truncate">{rule.params.location || label}</span>
                  <span className="text-[9px] text-stone-500 dark:text-stone-400">{label}</span>
                </motion.button>
              )
            })}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
