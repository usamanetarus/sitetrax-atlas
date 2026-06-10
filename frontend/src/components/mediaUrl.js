export function resolveMediaUrl(url) {
  if (!url || typeof url !== 'string') return ''
  if (/^(https?:)?\/\//i.test(url) || url.startsWith('data:') || url.startsWith('blob:')) return url
  if (url.startsWith('/api/')) return url
  if (url.startsWith('/')) {
    return import.meta.env.DEV ? `/api${url}` : url
  }
  return import.meta.env.DEV ? `/api/${url}` : url
}
