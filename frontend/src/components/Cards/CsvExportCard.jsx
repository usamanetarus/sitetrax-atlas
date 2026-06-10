import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'
function CsvExportCard({ data }) {
  const facility = data?.facility || 'Unknown'
  const rowCount = data?.row_count || 0
  const csvData = data?.csv_data || ''
  const rangeLabel = formatDateRange(data, 'requested range')

  const handleDownload = () => {
    const blob = new Blob([csvData], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${facility.replace(/[^a-zA-Z0-9]/g, '_')}_export.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">CSV Export: {facility}</h3>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-200">
          {rowCount} rows
        </span>
      </div>
      <div className="mb-3 rounded-md bg-stone-50 p-3 dark:bg-stone-900">
        <div className="text-xs text-stone-500 dark:text-stone-300">
          <div className="mb-1">Facility: {facility}</div>
          <div className="mb-1">Time window: {rangeLabel}</div>
          <div>Columns: container_id, type, status_code, datetime, location, camera, gps_lat, gps_lon, asset_heading, video_name</div>
        </div>
      </div>
      <button
        onClick={handleDownload}
        className="w-full rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-200 dark:hover:bg-stone-800/70"
      >
        Download CSV
      </button>
      <CardReferences items={[cardReferences.exportData, cardReferences.integrations, cardReferences.support]} />
    </div>
  )
}

export default CsvExportCard
