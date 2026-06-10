import { useEffect, useMemo, useState } from 'react'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { resolveMediaUrl } from '../mediaUrl'
import { formatDateRange } from './formatters'
function ReviewQueueCard({ data }) {
  const [resolvedItems, setResolvedItems] = useState([])
  const items = data?.items_needing_review || []
  const total = data?.total_detections || 0
  const needsReview = data?.needs_review_count || 0
  const rate = data?.review_rate_percent || 0
  const byStatus = data?.by_status_code || {}
  const facility = data?.facility || "Unknown"
  const rangeLabel = formatDateRange(data, 'recent window')
  const imageItems = useMemo(() => {
    const source = Array.isArray(data?.images) && data.images.length > 0 ? data.images : items
    return source
  }, [data?.images, items])
  const hasImages = resolvedItems.some((item) => item.image_url || item.asset_image || item.thumbnail_url || item.thumbnail) || imageItems.some((item) => item.image_url || item.asset_image || item.thumbnail_url || item.thumbnail)

  useEffect(() => {
    setResolvedItems(imageItems)
  }, [imageItems])

  useEffect(() => {
    let cancelled = false
    async function hydrate() {
      const next = await Promise.all(imageItems.map(async (item) => {
        const existing = resolveMediaUrl(item.image_url || item.asset_image || item.thumbnail_url || item.thumbnail || '')
        if (existing) return { ...item, image_url: existing }
        const assetId = item.asset_id || item.id
        if (!assetId) return item
        try {
          const response = await fetch(`/api/asset/${encodeURIComponent(assetId)}`)
          if (!response.ok) return item
          const detail = await response.json()
          const url = resolveMediaUrl(detail.asset_image || detail.image_url || detail.thumbnail_url || detail.thumbnail || detail.thumbnail_md || detail.thumbnail_hr || '')
          if (!url) return item
          return { ...item, image_url: url, asset_image: url, thumbnail_url: url }
        } catch {
          return item
        }
      }))
      if (!cancelled) setResolvedItems(next)
    }
    hydrate()
    return () => { cancelled = true }
  }, [imageItems])

  const statusColors = {
    A0: "text-emerald-700 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-300",
    A1: "text-stone-700 bg-stone-100 dark:bg-stone-800 dark:text-stone-200",
    I1: "text-amber-700 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-300",
    I2: "text-amber-700 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-300",
    I3: "text-stone-700 bg-stone-100 dark:bg-stone-800 dark:text-stone-200",
    I4: "text-stone-700 bg-stone-100 dark:bg-stone-800 dark:text-stone-200",
    I5: "text-red-700 bg-red-50 dark:bg-red-900/20",
    I6: "text-red-700 bg-red-50 dark:bg-red-900/20",
    I7: "text-red-700 bg-red-100 dark:bg-red-900/30",
  }

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4 dark:border-stone-700 dark:bg-stone-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-stone-950 dark:text-stone-50">
          Review Queue: {facility}
        </h3>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-300">
          {rangeLabel}
        </span>
      </div>
      <div className="mb-3 grid grid-cols-3 gap-2">
        <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{total}</div>
          <div className="text-[10px] text-stone-500 dark:text-stone-300">Total</div>
        </div>
        <div className="rounded-md bg-red-50 p-2 text-center dark:bg-red-900/10">
          <div className="text-lg font-bold text-red-600 dark:text-red-400">{needsReview}</div>
          <div className="text-[10px] text-red-500 dark:text-red-400">Need Review</div>
        </div>
        <div className="rounded-md bg-stone-50 p-2 text-center dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{rate}%</div>
          <div className="text-[10px] text-stone-500 dark:text-stone-300">Review Rate</div>
        </div>
      </div>
      {Object.keys(byStatus).length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {Object.entries(byStatus).map(([code, count]) => (
            <span key={code} className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${statusColors[code] || "text-stone-600 bg-stone-100 dark:bg-slate-800"}`}>
              {code}: {count}
            </span>
          ))}
        </div>
      )}
      {items.length > 0 && (
        <div className="max-h-48 overflow-auto rounded-md border border-stone-100 dark:border-stone-800">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-stone-50 dark:bg-stone-950">
              <tr>
                <th className="px-2 py-1 font-medium text-stone-500 dark:text-stone-300">Container</th>
                {hasImages && <th className="px-2 py-1 font-medium text-stone-500 dark:text-stone-300">Image</th>}
                <th className="px-2 py-1 font-medium text-stone-500 dark:text-stone-300">Status</th>
                <th className="px-2 py-1 font-medium text-stone-500 dark:text-stone-300">Time</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, i) => (
                <tr key={i} className="border-t border-stone-50 dark:border-stone-800">
                  <td className="px-2 py-1 font-mono text-stone-700 dark:text-stone-200">{item.text || item.container_id || "-"}</td>
                  {hasImages && (
                    <td className="px-2 py-1">
                      {(() => {
                        const hydrated = resolvedItems[i] || item
                        const imageUrl = resolveMediaUrl(hydrated.image_url || hydrated.asset_image || hydrated.thumbnail_url || hydrated.thumbnail || '')
                        return imageUrl ? (
                          <a
                            href={imageUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="block h-10 w-16 overflow-hidden rounded-md border border-stone-200 bg-stone-100 dark:border-stone-700 dark:bg-stone-900"
                          >
                            <img
                              src={imageUrl}
                              alt=""
                              className="h-full w-full object-cover"
                              referrerPolicy="no-referrer"
                              loading="lazy"
                            />
                          </a>
                        ) : (
                          <span className="text-[10px] text-stone-400">-</span>
                        )
                      })()}
                    </td>
                  )}
                  <td className="px-2 py-1">
                    <span className={`rounded px-1 text-[10px] font-semibold ${statusColors[item.status_code] || "text-stone-600 bg-stone-100"}`}>
                      {item.status_code}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-stone-500 dark:text-stone-300">
                    {item.datetime ? new Date(item.datetime).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {resolvedItems.some((item) => item.image_url || item.asset_image || item.thumbnail_url || item.thumbnail) && (
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {resolvedItems.map((item, index) => {
            const imageUrl = resolveMediaUrl(item.image_url || item.asset_image || item.thumbnail_url || item.thumbnail || '')
            if (!imageUrl) return null
            return (
              <a
                key={`${item.text || item.container_id || index}-${index}`}
                href={imageUrl}
                target="_blank"
                rel="noreferrer"
                className="group overflow-hidden rounded-lg border border-stone-200 bg-stone-50 dark:border-stone-800 dark:bg-stone-950"
              >
                <div className="aspect-video overflow-hidden bg-stone-100 dark:bg-stone-900">
                  <img
                    src={imageUrl}
                    alt=""
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                    referrerPolicy="no-referrer"
                    loading="lazy"
                  />
                </div>
                <div className="px-2 py-1 text-[10px] text-stone-500 dark:text-stone-300">
                  {item.text || item.container_id || '-'} · {item.status_code || '-'}
                </div>
              </a>
            )
          })}
        </div>
      )}
      <CardReferences items={[cardReferences.statusCodes, cardReferences.assetHeading, cardReferences.operationalInterpretation]} />
    </div>
  )
}

export default ReviewQueueCard
