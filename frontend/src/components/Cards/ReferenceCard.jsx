import { motion } from 'framer-motion'
import { Lightbulb, ArrowBendUpRight } from '../Icons'
import { SpotlightShell } from '../VisualEffects'

function FactList({ facts }) {
  return (
    <ul className="mt-1.5 space-y-1">
      {facts.map((fact, i) => (
        <li key={i} className="flex gap-2 text-xs leading-5 text-stone-600 dark:text-stone-200">
          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-stone-400 dark:bg-stone-500" />
          {fact}
        </li>
      ))}
    </ul>
  )
}

export default function ReferenceCard({ data }) {
  const matches = data.matches || []
  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <Lightbulb size={17} weight="duotone" />
            Documentation
          </div>
          <span className="text-xs text-stone-400 dark:text-stone-400">{matches.length} {matches.length === 1 ? 'result' : 'results'}</span>
        </div>
        {data.query && (
          <p className="mb-3 text-xs text-stone-500 dark:text-stone-300">
            <span className="font-semibold text-stone-700 dark:text-stone-200">Query:</span> {data.query}
          </p>
        )}
        <div className="space-y-3">
          {matches.slice(0, 3).map((match, i) => (
            <div key={i} className="rounded-lg border border-stone-100 bg-stone-50/80 p-3 dark:border-stone-800 dark:bg-stone-950">
              <div className="mb-1 text-xs font-semibold text-stone-800 dark:text-stone-100">{match.title}</div>
              <FactList facts={match.facts || []} />
              {match.source && (
                <a href={match.source.split(' ')[0]} target="_blank" rel="noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-[10px] text-stone-500 hover:underline dark:text-stone-300">
                  <ArrowBendUpRight size={10} weight="bold" />
                  {match.source.length > 60 ? match.source.slice(0, 60) + '…' : match.source}
                </a>
              )}
            </div>
          ))}
        </div>
      </motion.div>
    </SpotlightShell>
  )
}
