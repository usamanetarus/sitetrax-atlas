export function formatLocalDateTime(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  return new Intl.DateTimeFormat([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

export function formatDateRange(data = {}, fallback = 'requested range') {
  const from = data.date_from || data.created_at__gte || data.api_filters?.created_at__gte
  const to = data.date_to || data.created_at__lte || data.api_filters?.created_at__lte
  if (!from && !to) return fallback
  if (from && to) return `${formatLocalDateTime(from)} to ${formatLocalDateTime(to)}`
  if (from) return `from ${formatLocalDateTime(from)}`
  return `through ${formatLocalDateTime(to)}`
}

export function formatHeadingCounts(headings = {}) {
  const entries = Object.entries(headings)
  if (!entries.length) return 'Not recorded'
  return entries.map(([heading, count]) => `${heading}: ${count}`).join(', ')
}

export function formatFacilityCounts(byFacility = {}) {
  const entries = Object.entries(byFacility)
  if (!entries.length) return []
  return entries
}
