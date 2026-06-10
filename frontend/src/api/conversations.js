const STORAGE_KEY = 'sitetrax.conversations.v1'
const LAST_KEY = 'sitetrax.lastConversationId'
const REQUEST_TIMEOUT_MS = 3500

function readCache() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeCache(conversations) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations))
  } catch {}
}

function pruneCacheToIds(ids) {
  const idSet = new Set(ids)
  const next = readCache().map(normalizeConversation).filter((conversation) => (
    idSet.has(conversation.id) || idSet.has(conversation.sessionId)
  ))
  writeCache(next)
  if (next.length === 0 || !idSet.has(getLastConversationId())) {
    setLastConversationId(next[0]?.id || null)
  }
}

function normalizeMessage(message) {
  return {
    id: message.id || crypto.randomUUID(),
    role: message.role === 'user' ? 'user' : 'agent',
    text: message.text || '',
    cards: Array.isArray(message.cards) ? message.cards : [],
    timestamp: message.timestamp || new Date().toISOString(),
  }
}

function normalizeConversation(raw) {
  if (!raw || typeof raw !== 'object') return makeConversation()
  const record = raw.conversation || raw.session || raw.item || raw
  const id = raw.id || raw.session_id || raw.sessionId || crypto.randomUUID()
  const normalizedId = record.id || record.session_id || record.sessionId || id
  const messages = Array.isArray(record.messages) ? record.messages.map(normalizeMessage) : []
  const firstUser = messages.find((message) => message.role === 'user' && message.text)
  return {
    id: normalizedId,
    sessionId: record.session_id || record.sessionId || normalizedId,
    title: record.title || firstUser?.text?.slice(0, 64) || 'New conversation',
    messages,
    createdAt: record.created_at || record.createdAt || messages[0]?.timestamp || new Date().toISOString(),
    updatedAt: record.updated_at || record.updatedAt || messages.at(-1)?.timestamp || new Date().toISOString(),
    source: record.source || 'local',
  }
}

function summarize(conversation) {
  const last = conversation.messages.at(-1)
  return {
    id: conversation.id,
    sessionId: conversation.sessionId,
    title: conversation.title,
    createdAt: conversation.createdAt,
    updatedAt: conversation.updatedAt,
    preview: last?.text || last?.cards?.[0]?.type || '',
    messageCount: conversation.messages.length,
    source: conversation.source,
  }
}

function normalizeSessionSummary(raw) {
  const id = raw.id || raw.session_id || raw.sessionId
  return {
    id,
    sessionId: raw.session_id || raw.sessionId || id,
    title: raw.title || `Session ${String(id || '').slice(0, 8)}`,
    createdAt: raw.created_at || raw.createdAt || raw.last_update_time || raw.updatedAt || new Date().toISOString(),
    updatedAt: raw.last_update_time || raw.updated_at || raw.updatedAt || new Date().toISOString(),
    preview: raw.preview || '',
    messageCount: raw.message_count || raw.messageCount || 0,
    source: 'backend',
  }
}

async function requestJson(path, options) {
  const { timeoutMs, ...fetchOptions } = options || {}
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs || REQUEST_TIMEOUT_MS)
  let response
  try {
    response = await fetch(path, {
      ...fetchOptions,
      signal: fetchOptions.signal || controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(fetchOptions.headers || {}),
      },
    })
  } finally {
    clearTimeout(timeout)
  }
  if (!response.ok) {
    const error = new Error(`Request failed with ${response.status}`)
    error.status = response.status
    throw error
  }
  if (response.status === 204) return null
  return response.json()
}

export function getLastConversationId() {
  try {
    return localStorage.getItem(LAST_KEY)
  } catch {
    return null
  }
}

export function setLastConversationId(id) {
  try {
    if (id) localStorage.setItem(LAST_KEY, id)
    else localStorage.removeItem(LAST_KEY)
  } catch {}
}

export function makeConversation(title = 'New conversation') {
  const id = crypto.randomUUID()
  const now = new Date().toISOString()
  return {
    id,
    sessionId: id,
    title,
    messages: [],
    createdAt: now,
    updatedAt: now,
    source: 'local',
  }
}

export async function loadConversationSummaries() {
  const cached = readCache().map(normalizeConversation)
  try {
    const data = await requestJson('/api/chat/sessions')
    const rows = data?.sessions || data?.conversations || data?.items || data?.results || data || []
    const backend = rows
      .map(normalizeSessionSummary)
      .filter((item) => item.id && item.messageCount > 0)
    pruneCacheToIds(backend.map((item) => item.id))
    return {
      source: 'backend',
      conversations: backend.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt)),
    }
  } catch {}

  try {
    const data = await requestJson('/api/conversations')
    const rows = data?.conversations || data?.sessions || data?.items || data?.results || data || []
    const conversations = rows
      .map(normalizeConversation)
      .filter((conversation) => conversation.messages.length > 0)
      .map((conversation) => ({
        ...summarize(conversation),
        source: 'backend',
      }))
    pruneCacheToIds(conversations.map((conversation) => conversation.id))
    return {
      source: 'backend',
      conversations,
    }
  } catch {
    return {
      source: 'local',
      conversations: cached.map(summarize).filter((item) => item.messageCount > 0),
    }
  }
}

export async function loadConversation(id) {
  if (!id) return null
  const cached = readCache().map(normalizeConversation)
  const cachedMatch = cached.find((conversation) => conversation.id === id || conversation.sessionId === id)
  try {
    const data = await requestJson(`/api/chat/history/${encodeURIComponent(id)}`)
    const messages = Array.isArray(data?.messages) ? data.messages.map(normalizeMessage) : []
    // Accept the backend response if it includes a session_id (session exists)
    // even when messages are empty (e.g. events failed validation or session is new).
    if (data?.session_id || data?.sessionId || messages.length > 0) {
      return {
        id,
        sessionId: data?.session_id || data?.sessionId || id,
        title: cachedMatch?.title || buildTitle(messages) || 'Session',
        messages,
        createdAt: cachedMatch?.createdAt || messages[0]?.timestamp || new Date().toISOString(),
        updatedAt: messages.at(-1)?.timestamp || cachedMatch?.updatedAt || new Date().toISOString(),
        source: 'backend',
      }
    }
  } catch {}

  try {
    const data = await requestJson(`/api/conversations/${encodeURIComponent(id)}`)
    return { ...normalizeConversation(data), source: 'backend' }
  } catch {
    return cachedMatch || null
  }
}

export async function saveConversation(conversation) {
  const normalized = normalizeConversation(conversation)
  if (normalized.messages.length === 0) {
    setLastConversationId(normalized.id)
    return { source: 'local', conversation: normalized, skipped: true }
  }
  const cached = readCache().map(normalizeConversation)
  const next = [normalized, ...cached.filter((item) => item.id !== normalized.id)]
    .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
    .slice(0, 50)
  writeCache(next)
  setLastConversationId(normalized.id)

  try {
    const data = await requestJson(`/api/chat/history/${encodeURIComponent(normalized.sessionId)}`)
    const messages = Array.isArray(data?.messages) ? data.messages.map(normalizeMessage) : []
    if (messages.length > 0) {
      return {
        source: 'backend',
        conversation: {
          ...normalized,
          messages,
          updatedAt: messages.at(-1)?.timestamp || normalized.updatedAt,
          source: 'backend',
        },
      }
    }
  } catch {}

  try {
    const data = await requestJson(`/api/conversations/${encodeURIComponent(normalized.id)}`, {
      method: 'PUT',
      body: JSON.stringify({
        id: normalized.id,
        session_id: normalized.sessionId,
        title: normalized.title,
        messages: normalized.messages,
        created_at: normalized.createdAt,
        updated_at: normalized.updatedAt,
      }),
    })
    return { source: 'backend', conversation: data ? normalizeConversation(data) : normalized }
  } catch {
    try {
      const data = await requestJson('/api/conversations', {
        method: 'POST',
        body: JSON.stringify({
          id: normalized.id,
          session_id: normalized.sessionId,
          title: normalized.title,
          messages: normalized.messages,
          created_at: normalized.createdAt,
          updated_at: normalized.updatedAt,
        }),
      })
      return { source: 'backend', conversation: data ? normalizeConversation(data) : normalized }
    } catch {
      return { source: 'local' }
    }
  }
}

export async function deleteConversation(id) {
  const next = readCache().filter((conversation) => conversation.id !== id)
  writeCache(next)
  if (getLastConversationId() === id) setLastConversationId(next[0]?.id || null)
  try {
    await requestJson(`/api/chat/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
    return { source: 'backend' }
  } catch {}

  try {
    await requestJson(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
    return { source: 'backend' }
  } catch {
    return { source: 'local' }
  }
}

export function buildTitle(messages) {
  const firstUser = messages.find((message) => message.role === 'user' && message.text.trim())
  if (!firstUser) return 'New conversation'
  const text = firstUser.text.trim().replace(/\s+/g, ' ')
  return text.length > 54 ? `${text.slice(0, 54)}...` : text
}
