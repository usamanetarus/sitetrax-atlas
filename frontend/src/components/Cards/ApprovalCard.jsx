import { useState } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, XCircle, BellRinging } from '../Icons'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function ApprovalCard({ data }) {
  const [decided, setDecided] = useState(null)
  const action = data.action || 'unknown'
  const template = data.template || 'Monitoring rule'
  const params = data.params || {}
  const description = data.description || ''

  const handleApprove = () => {
    setDecided('approved')
    // Dispatch a synthetic event that App.jsx can catch
    window.dispatchEvent(new CustomEvent('approval-response', {
      detail: { action, approved: true, params, template: data.template_name || template }
    }))
  }

  const handleDeny = () => {
    setDecided('denied')
    window.dispatchEvent(new CustomEvent('approval-response', {
      detail: { action, approved: false }
    }))
  }

  if (decided === 'approved') {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-stone-50/80 p-4 dark:border-stone-700 dark:bg-stone-900"
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-stone-200">
          <CheckCircle size={16} weight="duotone" />
          Rule creation approved
        </div>
        <p className="mt-1 text-xs text-stone-500 dark:text-stone-300">
          The agent will create the {template} rule now.
        </p>
      </motion.div>
    )
  }

  if (decided === 'denied') {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-stone-50/80 p-4 dark:border-stone-700 dark:bg-stone-900"
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-stone-600 dark:text-stone-300">
          <XCircle size={16} weight="duotone" />
          Rule creation cancelled
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="min-w-[280px] rounded-xl border border-stone-200 bg-stone-50/80 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900"
    >
      <div className="mb-3 flex items-center gap-2">
        <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm dark:bg-stone-100 dark:text-stone-950">
          <BellRinging size={15} weight="duotone" />
          Needs Confirmation
        </div>
      </div>

      <div className="mb-2 text-sm font-semibold text-stone-800 dark:text-stone-100">
        Create {template}?
      </div>

      {description && (
        <div className="mb-2 text-xs text-stone-500 dark:text-stone-300">{description}</div>
      )}

      {Object.keys(params).length > 0 && (
        <div className="mb-3 rounded-lg border border-stone-200 bg-white/60 p-2 dark:border-stone-800 dark:bg-stone-950">
          {Object.entries(params).map(([k, v]) => (
            <div key={k} className="flex justify-between text-xs">
              <span className="text-stone-500 dark:text-stone-300">{k}:</span>
              <span className="font-mono font-medium text-stone-700 dark:text-stone-200">{String(v)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleApprove}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-stone-900 px-3 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-stone-800 dark:bg-stone-100 dark:text-stone-950 dark:hover:bg-white"
        >
          <CheckCircle size={14} weight="duotone" />
          Approve
        </button>
        <button
          onClick={handleDeny}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-600 shadow-sm transition-colors hover:bg-stone-50 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:hover:bg-stone-900/60"
        >
          <XCircle size={14} weight="duotone" />
          Deny
        </button>
      </div>
      <CardReferences items={[cardReferences.monitoringRules, cardReferences.support]} />
    </motion.div>
  )
}
