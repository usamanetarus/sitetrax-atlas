import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { formatDateRange } from './formatters'
function CameraHealthCard({ data }) {
  const cameras = data?.cameras || []
  const total = data?.total_detections || 0
  const cameraCount = data?.camera_count || 0
  const lowActivity = data?.low_activity_cameras || []
  const facility = data?.facility || 'Unknown'
  const rangeLabel = formatDateRange(data, 'recent window')

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-stone-950 dark:text-stone-50">Camera Health: {facility}</h3>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-300">{rangeLabel}</span>
      </div>
      <div className="mb-3 grid grid-cols-3 gap-2">
        <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{total}</div>
          <div className="text-[10px] text-stone-500 dark:text-stone-300">Detections</div>
        </div>
        <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{cameraCount}</div>
          <div className="text-[10px] text-stone-500 dark:text-stone-300">Cameras</div>
        </div>
        <div className={`rounded-md p-2 text-center ${lowActivity.length > 0 ? 'bg-red-50 dark:bg-red-900/10' : 'bg-emerald-50 dark:bg-emerald-950/20'}`}>
          <div className={`text-lg font-bold ${lowActivity.length > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-700 dark:text-emerald-300'}`}>{lowActivity.length}</div>
          <div className={`text-[10px] ${lowActivity.length > 0 ? 'text-red-500 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-300'}`}>Low Activity</div>
        </div>
      </div>
      {cameras.length > 0 && (
        <div className="max-h-48 overflow-auto rounded-md border border-stone-100 dark:border-stone-800">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-stone-50 dark:bg-stone-950">
              <tr>
                <th className="px-2 py-1 font-medium text-stone-500 dark:text-stone-300">Camera</th>
                <th className="px-2 py-1 font-medium text-stone-500 dark:text-stone-300">Detections</th>
                <th className="px-2 py-1 font-medium text-stone-500 dark:text-stone-300">A0 Rate</th>
              </tr>
            </thead>
            <tbody>
              {cameras.map((cam, i) => (
                <tr key={i} className="border-t border-stone-50 dark:border-stone-800">
                  <td className="px-2 py-1 font-medium text-stone-700 dark:text-stone-200">{cam.camera}</td>
                  <td className="px-2 py-1 text-stone-700 dark:text-stone-200">{cam.detection_count}</td>
                  <td className="px-2 py-1">
                    <span className={`rounded px-1 text-[10px] font-semibold ${cam.a0_rate_percent >= 90 ? 'text-emerald-700 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-300' : cam.a0_rate_percent >= 70 ? 'text-amber-700 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-300' : 'text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-300'}`}>
                      {cam.a0_rate_percent}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <CardReferences items={[cardReferences.videoCapture, cardReferences.cameraInstallation, cardReferences.statusCodes]} />
    </div>
  )
}

export default CameraHealthCard
