import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowBendUpRight, Lightbulb, CaretRight } from './Icons'

function LinkPill({ href, label }) {
  if (!href) return null
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-white px-2 py-0.5 text-[10px] font-medium text-stone-600 transition-colors hover:border-stone-300 hover:text-stone-900 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300 dark:hover:border-stone-600 dark:hover:text-stone-100"
    >
      <ArrowBendUpRight size={10} weight="bold" />
      {label}
    </a>
  )
}

export default function CardReferences({ items = [] }) {
  const refs = items.filter(Boolean)
  const [open, setOpen] = useState(false)
  if (refs.length === 0) return null

  return (
    <div className="mt-3 border-t border-stone-200 pt-3 dark:border-stone-700">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-2 rounded-md px-0 py-0 text-left text-[10px] font-semibold uppercase tracking-wide text-stone-400 transition-colors hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300"
        aria-expanded={open}
      >
        <span className="flex items-center gap-1.5">
          <Lightbulb size={12} weight="duotone" />
          References
        </span>
        <span className="flex items-center gap-1">
          {refs.length}
          <CaretRight size={12} weight="bold" className={`transition-transform ${open ? 'rotate-90' : ''}`} />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="card-references"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.25, 0.1, 0.25, 1] }}
            style={{ overflow: 'hidden' }}
          >
            <div className="mt-2 space-y-2">
              {refs.map((ref, index) => (
                <div key={`${ref.label}-${index}`} className="rounded-md border border-stone-100 bg-stone-50/70 p-2 dark:border-stone-700 dark:bg-stone-950">
                  <div className="text-[11px] font-semibold text-stone-700 dark:text-stone-200">{ref.label}</div>
                  <div className="mt-0.5 text-[10px] leading-4 text-stone-500 dark:text-stone-300">{ref.meaning}</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    <LinkPill href={ref.docsUrl} label="Docs" />
                    <LinkPill href={ref.websiteUrl} label="Website" />
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
