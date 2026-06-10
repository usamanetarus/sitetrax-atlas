import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
function FacilityHealthCheckCard({ data }) {
  const report = data?.report || data || {}
  const facility = report?.facility || data?.facility || "Unknown"
  const score = report?.health_score || data?.health_score || 0
  const rating = report?.health_rating || data?.health_rating || "Unknown"
  const inventory = report?.inventory_7d || 0
  const scans24h = report?.scans_24h || 0
  const inbound = report?.inbound_24h || 0
  const outbound = report?.outbound_24h || 0
  const a0Rate = report?.a0_rate_percent || 0
  const detention = report?.detention_risk || []
  const cameras = report?.cameras || []
  const statusDist = report?.status_distribution || {}

  const ratingColor = score >= 90 ? "text-green-600 bg-green-50 dark:bg-green-900/20" :
                      score >= 75 ? "text-blue-600 bg-blue-50 dark:bg-blue-900/20" :
                      score >= 50 ? "text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20" :
                      "text-red-600 bg-red-50 dark:bg-red-900/20"

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-stone-950 dark:text-stone-50">Facility Health: {facility}</h3>
        <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${ratingColor}`}>
          {rating} ({score}/100)
        </span>
      </div>
      <div className="mb-3 grid grid-cols-4 gap-2">
        <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{inventory}</div>
          <div className="text-[10px] text-stone-500 dark:text-stone-300">Containers (7d)</div>
        </div>
        <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{scans24h}</div>
          <div className="text-[10px] text-stone-500 dark:text-stone-300">Scans (24h)</div>
        </div>
        <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{a0Rate}%</div>
          <div className="text-[10px] text-stone-500 dark:text-stone-300">A0 Rate</div>
        </div>
        <div className={`rounded-md border p-2 text-center ${detention.length > 0 ? "border-red-200 bg-red-50 dark:border-red-900/30 dark:bg-red-950/20" : "border-stone-200 bg-stone-50 dark:border-stone-800 dark:bg-stone-950"}`}>
          <div className={`text-lg font-bold ${detention.length > 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>{detention.length}</div>
          <div className={`text-[10px] ${detention.length > 0 ? "text-red-500 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>Detention</div>
        </div>
      </div>
      {scans24h > 0 && (
        <div className="mb-3 flex items-center gap-3 rounded-md border border-stone-200 bg-stone-50 p-2 dark:border-stone-800 dark:bg-stone-950">
          <div className="flex-1 text-center">
            <div className="text-xs font-semibold text-green-600 dark:text-green-400">→ Inbound: {inbound}</div>
          </div>
          <div className="h-6 w-px bg-slate-200 dark:bg-stone-900"></div>
          <div className="flex-1 text-center">
            <div className="text-xs font-semibold text-blue-600 dark:text-blue-400">← Outbound: {outbound}</div>
          </div>
        </div>
      )}
      {Object.keys(statusDist).length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-[11px] font-semibold text-stone-500 dark:text-stone-300">Status Distribution</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(statusDist).map(([code, count]) => (
              <span key={code} className="rounded-md bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-600 dark:bg-stone-900 dark:text-stone-300">
                {code}: {count}
              </span>
            ))}
          </div>
        </div>
      )}
      {cameras.length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-[11px] font-semibold text-stone-500 dark:text-stone-300">Cameras</div>
          <div className="flex flex-wrap gap-1.5">
            {cameras.map((cam, i) => (
              <span key={i} className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cam.a0_rate >= 90 ? "text-emerald-700 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-300" : cam.a0_rate >= 70 ? "text-amber-700 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-300" : "text-red-600 bg-red-50 dark:bg-red-950/20 dark:text-red-300"}`}>
                {cam.camera} ({cam.detections}, {cam.a0_rate}%)
              </span>
            ))}
          </div>
        </div>
      )}
      {detention.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-semibold text-red-500 dark:text-red-400">Detention Risk</div>
          <div className="max-h-32 overflow-auto rounded-md border border-red-100 dark:border-red-900/20">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-red-50 dark:bg-red-900/10">
                <tr>
                  <th className="px-2 py-1 font-medium text-red-600 dark:text-red-400">Container</th>
                  <th className="px-2 py-1 font-medium text-red-600 dark:text-red-400">Dwell (h)</th>
                </tr>
              </thead>
              <tbody>
                {detention.map((d, i) => (
                  <tr key={i} className="border-t border-red-50 dark:border-red-900/10">
                    <td className="px-2 py-1 font-mono text-stone-700 dark:text-slate-300">{d.container_id}</td>
                    <td className="px-2 py-1 text-red-600 dark:text-red-400">{d.dwell_hours}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <CardReferences items={[cardReferences.statusCodes, cardReferences.assetHeading, cardReferences.facilityOverview, cardReferences.detention]} />
    </div>
  )
}

export default FacilityHealthCheckCard
