import { motion } from 'framer-motion'
import { MapPin, Package } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'

export default function ContainerCompanyCard({ data }) {
  const assets = data.assets || []
  const prefix = data.company_prefix || 'Unknown'
  const facility = data.facility || 'All facilities'
  const count = data.count || 0

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
            <MapPin size={17} weight="duotone" />
            {prefix} containers
          </div>
          <Package size={20} weight="duotone" className="text-stone-500 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{facility}</div>
          <div className="mt-1 text-xs text-stone-500 dark:text-stone-300">{count} assets from {prefix}</div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {assets.slice(0, 30).map((a, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-stone-50 px-2 py-1 font-mono text-xs text-stone-700 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200">
              {a.text || 'N/A'}
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${a.status_code === 'A0' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
            </span>
          ))}
        </div>
        <CardReferences items={[cardReferences.assetSchema, cardReferences.statusCodes]} />
      </motion.div>
    </SpotlightShell>
  )
}
