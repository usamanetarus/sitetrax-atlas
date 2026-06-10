import { motion } from 'framer-motion'
import { MagnifyingGlass, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import { formatLocalDateTime } from './formatters'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

function StatusBadge({ code }) {
  const color = code === 'A0' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
    : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
  return <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${color}`}>{code || '—'}</span>
}

export default function SearchResultsCard({ data }) {
  const assets = data.assets || []
  return (
    <SpotlightShell className="rounded-xl">
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <MagnifyingGlass size={17} weight="duotone" />
            Asset search
          </div>
          <div className="text-right">
            <div className="text-xl font-semibold text-stone-800 dark:text-stone-200">{data.count ?? assets.length}</div>
            <div className="text-[10px] font-semibold uppercase text-stone-600 dark:text-stone-300">results</div>
          </div>
        </div>
        {data.query && (
          <p className="mb-2 text-xs text-stone-500 dark:text-stone-300">
            <span className="font-semibold text-stone-700 dark:text-stone-200">Query:</span> {data.query}
          </p>
        )}
        <div className="space-y-1.5">
          {assets.slice(0, 8).map((asset, i) => (
            <div key={i} className="flex items-center justify-between gap-2 rounded-lg border border-stone-100 bg-stone-50/80 px-2.5 py-2 dark:border-stone-800 dark:bg-stone-950">
              <div className="flex items-center gap-2 min-w-0">
                <Package size={14} weight="duotone" className="shrink-0 text-stone-500 dark:text-stone-200" />
                <span className="truncate font-mono text-xs font-semibold text-stone-800 dark:text-stone-100">{asset.text || asset.container_id || '—'}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <StatusBadge code={asset.status_code} />
                <span className="text-[10px] text-stone-400 dark:text-stone-400">{asset.location ? asset.location.split(' ')[0] : ''}</span>
              </div>
            </div>
          ))}
          {assets.length === 0 && (
            <p className="py-3 text-center text-xs text-stone-400 dark:text-stone-400">No assets found</p>
          )}
        </div>
        {(data.count ?? 0) > 8 && (
          <p className="mt-2 text-center text-[10px] text-stone-400 dark:text-stone-400">
            Showing 8 of {data.count} results
          </p>
        )}
        <CardReferences items={[cardReferences.searchResults, cardReferences.statusCodes]} />
      </motion.div>
    </SpotlightShell>
  )
}
