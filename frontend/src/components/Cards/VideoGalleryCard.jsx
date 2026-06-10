import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { VideoCamera, Clock, MapPin } from '../Icons'
import { SpotlightShell } from '../VisualEffects'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { resolveMediaUrl } from '../mediaUrl'

function formatTime(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export default function VideoGalleryCard({ data }) {
  const container_id = data.container_id || ''
  const videos = data.videos || []
  const count = data.count || videos.length

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
            <VideoCamera size={17} weight="duotone" />
            Video clips
            <span className="ml-0.5 rounded-full bg-white/20 px-1.5 py-0 text-[10px]">{count}</span>
          </div>
          {container_id && (
            <div className="font-mono text-sm font-semibold text-stone-900 dark:text-stone-100">{container_id}</div>
          )}
        </div>

        <div className="custom-scrollbar -mr-1 flex gap-2.5 overflow-x-auto pb-2 pr-1">
          {videos.map((video, i) => (
            <VideoThumbnail key={video.video_id || i} video={video} index={i} />
          ))}
        </div>
      </motion.div>
    </SpotlightShell>
  )
}

function VideoThumbnail({ video, index }) {
  const url = video.url || ''
  const videoId = video.video_id || ''
  const detectedAt = video.detected_at || ''
  const facility = video.facility || 'Unknown'
  const initialThumbnail = resolveMediaUrl(video.thumbnail_url || video.thumbnail_md || video.thumbnail || video.thumbnail_hr || '')
  const [thumbnail, setThumbnail] = useState(initialThumbnail)

  useEffect(() => {
    setThumbnail(initialThumbnail)
  }, [initialThumbnail])

  useEffect(() => {
    if (thumbnail || !videoId) return undefined
    const controller = new AbortController()
    fetch(`/api/video/${encodeURIComponent(videoId)}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((detail) => {
        if (detail) {
          const nextThumbnail = resolveMediaUrl(detail.thumbnail_url || detail.thumbnail_md || detail.thumbnail || detail.thumbnail_hr || '')
          if (nextThumbnail) setThumbnail(nextThumbnail)
        }
      })
      .catch(() => {})
    return () => controller.abort()
  }, [thumbnail, videoId])

  return (
    <motion.div
      initial={{ opacity: 0, x: 8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25, delay: index * 0.05 }}
      className="flex w-48 shrink-0 flex-col rounded-lg border border-stone-200 bg-white p-2.5 dark:border-stone-700 dark:bg-stone-900"
    >
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="group relative mb-2 flex aspect-video items-center justify-center overflow-hidden rounded-md bg-stone-100 dark:bg-stone-950"
        >
          {thumbnail ? (
            <img src={thumbnail} alt="" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]" />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-stone-900 text-white shadow-lg transition-transform group-hover:scale-110 dark:bg-stone-100 dark:text-stone-950">
                <VideoCamera size={18} weight="duotone" />
              </div>
            </div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/25 via-transparent to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
          <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1 py-0.5 text-[9px] font-medium text-white">
            Open
          </span>
        </a>
      ) : (
        <div className="mb-2 flex aspect-video items-center justify-center rounded-md bg-stone-100 dark:bg-stone-950">
          <VideoCamera size={20} weight="duotone" className="text-stone-300 dark:text-stone-600" />
        </div>
      )}
      <div className="flex flex-1 flex-col gap-1">
        <div className="truncate text-[11px] font-semibold text-stone-700 dark:text-stone-200">
          {facility}
        </div>
        {videoId && (
          <div className="truncate text-[10px] text-stone-400 dark:text-stone-400">ID: {String(videoId).slice(0, 12)}…</div>
        )}
        {detectedAt && (
          <div className="mt-auto flex items-center gap-1 text-[10px] text-stone-400 dark:text-stone-400">
            <Clock size={10} weight="duotone" />
            {formatTime(detectedAt)}
          </div>
        )}
      </div>
      <CardReferences items={[cardReferences.videoCapture, cardReferences.videoSchema]} />
    </motion.div>
  )
}
