import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'
function FacilityReportCard({ data }) {
  const report = data?.report || data || {}
  const facility = report?.facility || data?.facility || "Unknown"
  const rangeLabel = formatDateRange(data, report?.days_covered ? `${report.days_covered} days` : 'requested range')
  const summary = report?.summary || {}
  const statusDist = report?.status_distribution || {}
  const detention = report?.detention_risk || []
  const topContainers = report?.top_containers || []

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Facility Report: {facility}</h3>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-200">{rangeLabel}</span>
      </div>
      {summary && (
        <div className="mb-3 grid grid-cols-3 gap-2">
          <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
            <div className="text-lg font-bold text-stone-900 dark:text-stone-100">{summary.total_containers_7d || 0}</div>
            <div className="text-[10px] text-stone-500 dark:text-stone-300">Containers (7d)</div>
          </div>
          <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
            <div className="text-lg font-bold text-stone-900 dark:text-stone-100">{summary.total_scans_24h || 0}</div>
            <div className="text-[10px] text-stone-500 dark:text-stone-300">Scans (24h)</div>
          </div>
          <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
            <div className="text-lg font-bold text-stone-900 dark:text-stone-100">{summary.a0_rate_percent || 0}%</div>
            <div className="text-[10px] text-stone-500 dark:text-stone-300">A0 Rate</div>
          </div>
        </div>
      )}
      {Object.keys(statusDist).length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-[11px] font-semibold text-stone-500 dark:text-stone-300">Status Distribution</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(statusDist).map(([code, count]) => (
              <span key={code} className="rounded-md bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                {code}: {count}
              </span>
            ))}
          </div>
        </div>
      )}
      {detention.length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-[11px] font-semibold text-stone-600 dark:text-stone-300">Detention Risk ({detention.length})</div>
          <div className="max-h-32 overflow-auto rounded-md border border-stone-200 dark:border-stone-800">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-stone-50 dark:bg-stone-950">
                <tr>
                  <th className="px-2 py-1 font-medium text-stone-600 dark:text-stone-200">Container</th>
                  <th className="px-2 py-1 font-medium text-stone-600 dark:text-stone-200">Dwell (h)</th>
                </tr>
              </thead>
              <tbody>
                {detention.map((d, i) => (
                  <tr key={i} className="border-t border-stone-100 dark:border-stone-800">
                    <td className="px-2 py-1 font-mono text-stone-700 dark:text-stone-200">{d.container_id}</td>
                    <td className="px-2 py-1 text-stone-600 dark:text-stone-200">{d.dwell_hours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {topContainers.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-semibold text-stone-500 dark:text-stone-300">Recent Containers</div>
          <div className="flex flex-wrap gap-1.5">
            {topContainers.slice(0, 8).map((c, i) => (
              <span key={i} className="rounded-md bg-stone-100 px-1.5 py-0.5 text-[10px] font-mono text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                {c.container_id}
              </span>
            ))}
          </div>
        </div>
      )}
      <CardReferences items={[cardReferences.statusCodes, cardReferences.assetHeading, cardReferences.facilityOverview, cardReferences.exportData]} />
    </div>
  )
}

export default FacilityReportCard
