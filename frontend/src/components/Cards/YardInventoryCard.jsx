import { motion } from 'framer-motion'
import { Package, Rows } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import { formatDateRange, formatLocalDateTime } from './formatters'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function YardInventoryCard({ data }) {
  const assets = data.assets || []
  const facility = data.facility || 'Unknown'
  const count = data.count || 0
  const rangeLabel = formatDateRange(data, 'requested range')

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
            <Rows size={17} weight="duotone" />
            Yard inventory
          </div>
          <Package size={20} weight="duotone" className="text-stone-500 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{facility}</div>
          <div className="mt-1 text-xs text-stone-500 dark:text-stone-300">{count} assets detected · {rangeLabel}</div>
        </div>
        <div className="max-h-[280px] overflow-y-auto rounded-lg border border-stone-200 dark:border-stone-800">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-stone-50 dark:bg-stone-950">
              <tr>
                <th className="px-2 py-1.5 text-left font-semibold text-stone-600 dark:text-stone-300">Container</th>
                <th className="px-2 py-1.5 text-left font-semibold text-stone-600 dark:text-stone-300">Status</th>
                <th className="px-2 py-1.5 text-left font-semibold text-stone-600 dark:text-stone-300">Heading</th>
                <th className="px-2 py-1.5 text-left font-semibold text-stone-600 dark:text-stone-300">Time</th>
              </tr>
            </thead>
            <tbody>
              {assets.slice(0, 20).map((a, i) => (
                <tr key={i} className="border-t border-stone-100 dark:border-stone-800">
                  <td className="px-2 py-1.5 font-mono text-stone-800 dark:text-stone-200">{a.text || 'N/A'}</td>
                  <td className="px-2 py-1.5">
                    <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold ${a.status_code === 'A0' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300' : 'bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300'}`}>
                      {a.status_code || 'N/A'}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-stone-600 dark:text-stone-300">{a.asset_heading || '-'}</td>
                  <td className="px-2 py-1.5 text-stone-500 dark:text-stone-400">{formatLocalDateTime(a.datetime)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <CardReferences items={[cardReferences.facilityOverview, cardReferences.assetHeading, cardReferences.statusCodes]} />
      </motion.div>
    </SpotlightShell>
  )
}
