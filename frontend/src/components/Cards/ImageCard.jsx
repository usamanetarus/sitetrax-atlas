import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Image, Clock, MapPin, ListBullets, CaretRight } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { resolveMediaUrl } from '../mediaUrl'

export default function ImageCard({ data }) {
  const containerId = data.container_id || data.containerId || data.text || data.container || 'Unknown'
  const assetId = data.asset_id || data.assetId || data.id || ''
  const imageUrl = data.image_url || data.asset_image || ''
  const detectedAt = data.detected_at || data.datetime || ''
  const facility = data.facility || data.location || 'Unknown'
  const statusCode = data.status_code || data.statusCode || ''
  const heading = data.heading || data.asset_heading || ''
  const initialImage = resolveMediaUrl(imageUrl)
  const [resolvedImage, setResolvedImage] = useState(initialImage)

  useEffect(() => {
    setResolvedImage(initialImage)
  }, [initialImage])

  useEffect(() => {
    if (resolvedImage || !assetId) return undefined
    const controller = new AbortController()
    fetch(`/api/asset/${encodeURIComponent(assetId)}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((detail) => {
        if (detail) {
          const nextImage = resolveMediaUrl(detail.asset_image || detail.image_url || detail.thumbnail_url || detail.thumbnail || detail.thumbnail_md || detail.thumbnail_hr || '')
          if (nextImage) setResolvedImage(nextImage)
        }
      })
      .catch(() => {})
    return () => controller.abort()
  }, [assetId, resolvedImage])

  const handleSeeAll = () => {
    if (!containerId || containerId === 'Unknown') return
    window.dispatchEvent(new CustomEvent('image-gallery-request', { detail: { containerId } }))
  }

  const canOpen = Boolean(resolvedImage)

  return (
    <SpotlightShell className="rounded-xl">
      <motion.div
        initial={{ opacity: 0, y: 8, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="min-w-[280px] rounded-xl border border-stone-200 bg-white/95 p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm shadow-stone-950/15 dark:bg-stone-100 dark:text-stone-950">
            <Image size={17} weight="duotone" />
            Asset image
          </div>
          <Image size={20} weight="duotone" className="text-stone-400 dark:text-stone-200" />
        </div>
        <div className="mb-3">
          <div className="font-mono text-sm font-semibold text-stone-900 dark:text-stone-100">{containerId}</div>
          {assetId && <div className="mt-1 text-xs text-stone-500 dark:text-stone-300">Asset ID: {assetId}</div>}
        </div>
        {canOpen ? (
          <a
            href={resolvedImage}
            target="_blank"
            rel="noreferrer"
            className="group mb-3 overflow-hidden rounded-xl border border-stone-200 bg-stone-50 transition-colors hover:border-stone-300 hover:bg-stone-100 dark:border-stone-800 dark:bg-stone-950 dark:hover:border-stone-700 dark:hover:bg-stone-900/65"
          >
            <div className="relative aspect-video w-full overflow-hidden bg-stone-100 dark:bg-stone-900">
              <img
                src={resolvedImage}
                alt=""
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                referrerPolicy="no-referrer"
                loading="lazy"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-transparent" />
              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between p-3">
                <div className="inline-flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-semibold text-white backdrop-blur-sm">
                  <CaretRight size={11} weight="bold" />
                  Open image
                </div>
                <div className="text-[10px] text-white/80">Public asset image</div>
              </div>
            </div>
          </a>
        ) : (
          <div className="mb-3 rounded-xl border border-stone-200 bg-stone-50 p-6 text-center dark:border-stone-800 dark:bg-stone-950">
            <Image size={32} weight="duotone" className="mx-auto mb-2 text-stone-300 dark:text-stone-600" />
            <div className="text-sm text-stone-500 dark:text-stone-300">No image available</div>
            <div className="mt-1 text-xs text-stone-400 dark:text-stone-400">The detection may not have an associated asset image</div>
          </div>
        )}
        <div className="mb-3 flex flex-wrap gap-2">
          {facility && (
            <span className="inline-flex items-center gap-1 rounded-md bg-stone-100 px-2 py-1 text-xs text-stone-600 dark:bg-stone-800 dark:text-stone-200">
              <MapPin size={12} weight="duotone" /> {facility}
            </span>
          )}
          {detectedAt && (
            <span className="inline-flex items-center gap-1 rounded-md bg-stone-100 px-2 py-1 text-xs text-stone-600 dark:bg-stone-800 dark:text-stone-200">
              <Clock size={12} weight="duotone" /> {detectedAt}
            </span>
          )}
          {statusCode && (
            <span className="inline-flex items-center gap-1 rounded-md bg-stone-100 px-2 py-1 text-xs text-stone-600 dark:bg-stone-800 dark:text-stone-200">
              {statusCode}
            </span>
          )}
          {heading && (
            <span className="inline-flex items-center gap-1 rounded-md bg-stone-100 px-2 py-1 text-xs text-stone-600 dark:bg-stone-800 dark:text-stone-200">
              {heading}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleSeeAll}
          disabled={!containerId || containerId === 'Unknown'}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-medium text-stone-700 transition-colors hover:border-stone-300 hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:hover:border-stone-700 dark:hover:bg-stone-900/50"
        >
          <ListBullets size={15} weight="duotone" />
          See all images
        </button>
        <CardReferences items={[cardReferences.assetSchema, cardReferences.statusCodes, cardReferences.operationalInterpretation]} />
      </motion.div>
    </SpotlightShell>
  )
}
