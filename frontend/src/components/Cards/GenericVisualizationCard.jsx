import { useMemo, useState } from 'react'
import CardReferences from '../CardReferences.jsx'
import { cardReferences } from '../cardReferences.js'
import { resolveMediaUrl } from '../mediaUrl'
import { formatLocalDateTime } from './formatters'

function getDataset(data, name) {
  const datasets = Array.isArray(data?.datasets) ? data.datasets : []
  return datasets.find((dataset) => dataset.name === name) || datasets[0] || { rows: [], columns: [] }
}

function scalar(value) {
  if (value == null) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function pickLabel(row, index) {
  return row.text || row.container_id || row.name || row.facility || row.location || row.created_at_day || row.created_at || row.datetime || `Row ${index + 1}`
}

function pickNumericKey(rows) {
  const ignored = new Set(['id', 'bucket_id', 'gps_lat', 'gps_lon'])
  const counts = {}
  rows.forEach((row) => {
    Object.entries(row || {}).forEach(([key, value]) => {
      if (ignored.has(key) || key === 'raw_payload') return
      if (typeof value === 'number' && Number.isFinite(value)) counts[key] = (counts[key] || 0) + 1
    })
  })
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0]
}

function DownloadBlock({ download }) {
  if (!download?.content) return null
  const handleDownload = () => {
    const blob = new Blob([download.content], { type: download.mime_type || 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = download.filename || 'sitetrax-report.json'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
  return (
    <button
      onClick={handleDownload}
      className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-xs font-semibold text-stone-800 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100 dark:hover:bg-stone-900"
    >
      Download {download.filename || 'report'}
    </button>
  )
}

function MetricGrid({ rows }) {
  const row = rows[0] || {}
  const metrics = Object.entries(row)
    .filter(([key, value]) => key !== 'raw_payload' && typeof value === 'number' && Number.isFinite(value))
    .slice(0, 6)
  if (!metrics.length) return null
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {metrics.map(([key, value]) => (
        <div key={key} className="rounded-md border border-stone-200 bg-stone-50 p-3 text-center dark:border-stone-800 dark:bg-stone-950">
          <div className="text-lg font-bold text-stone-950 dark:text-stone-50">{value}</div>
          <div className="text-[10px] uppercase text-stone-500 dark:text-stone-400">{key.replaceAll('_', ' ')}</div>
        </div>
      ))}
    </div>
  )
}

function SortableTable({ dataset }) {
  const rows = dataset.rows || []
  const columns = (dataset.columns?.length ? dataset.columns : Object.keys(rows[0] || {}).filter((key) => key !== 'raw_payload').map((key) => ({ key, label: key }))).slice(0, 10)
  const [sortKey, setSortKey] = useState(columns[0]?.key || '')
  const [direction, setDirection] = useState('asc')
  const sorted = useMemo(() => {
    if (!sortKey) return rows
    return [...rows].sort((a, b) => {
      const av = a?.[sortKey]
      const bv = b?.[sortKey]
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : scalar(av).localeCompare(scalar(bv))
      return direction === 'asc' ? cmp : -cmp
    })
  }, [rows, sortKey, direction])
  if (!rows.length) return <div className="rounded-md border border-stone-200 p-3 text-sm text-stone-500 dark:border-stone-800 dark:text-stone-400">No rows returned.</div>
  return (
    <div className="max-h-80 overflow-auto rounded-md border border-stone-200 dark:border-stone-800">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-stone-100 dark:bg-stone-950">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="whitespace-nowrap px-2 py-1.5 font-semibold text-stone-600 dark:text-stone-300">
                <button
                  onClick={() => {
                    if (sortKey === column.key) setDirection((value) => (value === 'asc' ? 'desc' : 'asc'))
                    setSortKey(column.key)
                  }}
                  className="text-left"
                >
                  {column.label || column.key}{sortKey === column.key ? (direction === 'asc' ? ' ↑' : ' ↓') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, 100).map((row, index) => (
            <tr key={row.id || index} className="border-t border-stone-100 dark:border-stone-800">
              {columns.map((column) => (
                <td key={column.key} className="max-w-56 truncate px-2 py-1.5 text-stone-700 dark:text-stone-200" title={scalar(row?.[column.key])}>
                  {scalar(row?.[column.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Timeline({ rows }) {
  const sorted = [...rows].sort((a, b) => new Date(a.datetime || a.created_at || 0) - new Date(b.datetime || b.created_at || 0))
  if (!sorted.length) return null
  return (
    <div className="space-y-2">
      {sorted.slice(0, 20).map((row, index) => (
        <div key={row.id || index} className="flex gap-3 rounded-md border border-stone-200 bg-stone-50 p-2 dark:border-stone-800 dark:bg-stone-950">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-stone-900 text-xs font-semibold text-white dark:bg-stone-100 dark:text-stone-950">{index + 1}</div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-stone-900 dark:text-stone-100">{pickLabel(row, index)}</div>
            <div className="text-xs text-stone-500 dark:text-stone-400">{formatLocalDateTime(row.datetime || row.created_at)} · {row.location || row.facility || 'Unknown'}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

function MediaGallery({ rows, type }) {
  const isVideo = type === 'video_gallery'
  const items = rows.filter((row) => {
    if (isVideo) return row.url || row.video_url
    return row.image_url || row.asset_image || row.thumbnail_url || row.thumbnail
  })
  if (!items.length) return null
  return (
    <div className="custom-scrollbar flex gap-2 overflow-x-auto pb-2">
      {items.slice(0, 30).map((row, index) => {
        const image = resolveMediaUrl(row.image_url || row.asset_image || row.thumbnail_url || row.thumbnail || '')
        const thumb = resolveMediaUrl(row.thumbnail_url || row.thumbnail || row.thumbnail_md || row.thumbnail_hr || image || '')
        const videoHref = resolveMediaUrl(row.url || row.video_url || '')
        const href = isVideo ? videoHref : image
        return (
          <a key={row.id || row.asset_id || row.video_id || index} href={href || undefined} target="_blank" rel="noreferrer" className="w-48 shrink-0 rounded-md border border-stone-200 bg-white p-2 dark:border-stone-800 dark:bg-stone-950">
            <div className="mb-2 flex aspect-video items-center justify-center overflow-hidden rounded bg-stone-100 dark:bg-stone-900">
              {thumb ? <img src={thumb} alt="" className="h-full w-full object-cover" referrerPolicy="no-referrer" /> : <span className="text-xs text-stone-400">No preview</span>}
            </div>
            <div className="truncate text-xs font-semibold text-stone-800 dark:text-stone-100">{pickLabel(row, index)}</div>
            <div className="truncate text-[10px] text-stone-500 dark:text-stone-400">{formatLocalDateTime(row.detected_at || row.datetime || row.created_at)}</div>
          </a>
        )
      })}
    </div>
  )
}

function SimpleChart({ rows, type }) {
  const key = pickNumericKey(rows)
  if (!key || !rows.length) return null
  const points = rows.slice(0, 20).map((row, index) => ({ label: pickLabel(row, index), value: Number(row[key] || 0) }))
  const max = Math.max(...points.map((p) => p.value), 1)
  if (type === 'line') {
    const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${10 + i * (280 / Math.max(points.length - 1, 1))} ${110 - (p.value / max) * 90}`).join(' ')
    return <svg viewBox="0 0 300 120" className="h-36 w-full rounded-md border border-stone-200 bg-stone-50 dark:border-stone-800 dark:bg-stone-950"><path d={path} fill="none" stroke="currentColor" strokeWidth="2" className="text-stone-800 dark:text-stone-100" /></svg>
  }
  if (type === 'pie') {
    return <div className="text-xs text-stone-500 dark:text-stone-400">Pie view uses the same values as the table for `{key}`.</div>
  }
  return (
    <div className="space-y-1.5">
      {points.map((point) => (
        <div key={point.label} className="flex items-center gap-2 text-xs">
          <div className="w-28 truncate text-stone-500 dark:text-stone-400">{point.label}</div>
          <div className="h-2 flex-1 rounded-full bg-stone-100 dark:bg-stone-800">
            <div className="h-full rounded-full bg-stone-800 dark:bg-stone-200" style={{ width: `${Math.round((point.value / max) * 100)}%` }} />
          </div>
          <div className="w-12 text-right font-semibold text-stone-800 dark:text-stone-100">{point.value}</div>
        </div>
      ))}
    </div>
  )
}

function RawPayloads({ rows }) {
  const rawRows = rows.filter((row) => row.raw_payload)
  if (!rawRows.length) return null
  return (
    <details className="rounded-md border border-stone-200 bg-stone-50 p-2 dark:border-stone-800 dark:bg-stone-950">
      <summary className="cursor-pointer text-xs font-semibold text-stone-600 dark:text-stone-300">Raw payloads ({rawRows.length})</summary>
      <pre className="mt-2 max-h-72 overflow-auto text-[11px] text-stone-700 dark:text-stone-200">{JSON.stringify(rawRows.map((row) => row.raw_payload), null, 2)}</pre>
    </details>
  )
}

export default function GenericVisualizationCard({ data }) {
  const visualizations = Array.isArray(data?.visualizations) ? data.visualizations : []
  const dataset = getDataset(data, visualizations[0]?.dataset)
  const rows = dataset.rows || []
  const visibleVisualizations = visualizations.filter((viz) => viz.type !== 'json')
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm dark:border-stone-700 dark:bg-stone-900">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-stone-950 dark:text-stone-50">{data.title || dataset.label || 'SiteTrax data'}</h3>
          {data.answer && <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">{data.answer}</p>}
        </div>
        <DownloadBlock download={data.download} />
      </div>
      <div className="space-y-3">
        {visibleVisualizations.map((viz, index) => {
          const current = getDataset(data, viz.dataset)
          const currentRows = current.rows || []
          if (viz.type === 'metric_grid') return <MetricGrid key={index} rows={currentRows} />
          if (viz.type === 'timeline') return <Timeline key={index} rows={currentRows} />
          if (viz.type === 'image_gallery' || viz.type === 'video_gallery') return <MediaGallery key={index} rows={currentRows} type={viz.type} />
          if (['bar', 'line', 'pie'].includes(viz.type)) return <SimpleChart key={index} rows={currentRows} type={viz.type} />
          if (viz.type === 'table') return <SortableTable key={index} dataset={current} />
          return null
        })}
        {!visibleVisualizations.some((viz) => viz.type === 'table') && <SortableTable dataset={dataset} />}
        <RawPayloads rows={rows} />
      </div>
      <div className="mt-3 border-t border-stone-200 pt-2 text-[10px] text-stone-500 dark:border-stone-800 dark:text-stone-400">
        {data.provenance?.endpoint ? `${data.provenance.endpoint} · ${data.provenance.returned ?? rows.length} rows` : `${rows.length} rows`}
      </div>
      <CardReferences items={[cardReferences.assetSchema, cardReferences.facilityMetrics, cardReferences.videoSchema]} />
    </div>
  )
}
