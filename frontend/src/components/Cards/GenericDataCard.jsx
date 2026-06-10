import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
function GenericDataCard({ title, data }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
      <h3 className="mb-2 text-sm font-semibold text-stone-900 dark:text-stone-100">{title}</h3>
      <pre className="max-h-64 overflow-auto rounded-md bg-stone-50 p-2 text-xs text-stone-700 dark:bg-stone-950 dark:text-stone-200">
        {JSON.stringify(data, null, 2)}
      </pre>
      <CardReferences items={[cardReferences.assetSchema, cardReferences.support]} />
    </div>
  )
}

export default GenericDataCard
