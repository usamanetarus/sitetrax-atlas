import { useState, useRef, useEffect, useCallback } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import ChatMessages from './components/ChatMessages'
import ChatInput from './components/ChatInput'
import SimulateBar from './components/SimulateBar'
import { AppBackground } from './components/VisualEffects'
import {
  buildTitle,
  deleteConversation,
  getLastConversationId,
  loadConversation,
  loadConversationSummaries,
  makeConversation,
  saveConversation,
  setLastConversationId,
} from './api/conversations'

function App() {
  const [conversationId, setConversationId] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [conversationCreatedAt, setConversationCreatedAt] = useState(null)
  const [conversations, setConversations] = useState([])
  const [persistence, setPersistence] = useState({ state: 'loading', source: 'local', detail: 'Loading conversations' })
  const [hydrated, setHydrated] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [queuedMessage, setQueuedMessage] = useState('')
  const [toolInProgress, setToolInProgress] = useState(null)
  const [conversationLoading, setConversationLoading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [deletingRuleId, setDeletingRuleId] = useState(null)
  const [deletingOpportunityId, setDeletingOpportunityId] = useState(null)
  const [simulating, setSimulating] = useState(false)
  const [composerFocusToken, setComposerFocusToken] = useState(0)
  const [rules, setRules] = useState([])
  const [ruleTemplates, setRuleTemplates] = useState([])
  const [opportunities, setOpportunities] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(() => (
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 1024px)').matches : false
  ))
  const [backendStatus, setBackendStatus] = useState({
    state: 'checking',
    label: 'Checking backend',
    detail: 'Pinging FastAPI',
  })
  const chatEndRef = useRef(null)
  const userStartedConversationRef = useRef(false)
  const sendMessageRef = useRef(null)

  const activateConversation = useCallback((conversation) => {
    const normalized = conversation || makeConversation()
    setConversationId(normalized.id)
    setSessionId(normalized.sessionId || normalized.id)
    setConversationCreatedAt(normalized.createdAt || new Date().toISOString())
    setMessages(normalized.messages || [])
    setLastConversationId(normalized.id)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function hydrateConversations() {
      const { conversations: loaded, source } = await loadConversationSummaries()
      if (cancelled) return
      if (userStartedConversationRef.current) {
        setConversations((prev) => (
          prev.length
            ? prev
            : loaded
        ))
        setPersistence({
          state: source === 'backend' ? 'synced' : 'local',
          source,
          detail: source === 'backend' ? 'Conversations synced' : 'Using local conversation cache',
        })
        setHydrated(true)
        return
      }
      setConversations(loaded)
      const preferredId = getLastConversationId()
      const targetId = loaded.find((conversation) => conversation.id === preferredId)?.id || loaded[0]?.id
      const target = targetId ? await loadConversation(targetId) : makeConversation()
      if (cancelled) return
      activateConversation(target || makeConversation())
      setPersistence({
        state: source === 'backend' ? 'synced' : 'local',
        source,
        detail: source === 'backend' ? 'Conversations synced' : 'Using local conversation cache',
      })
      setHydrated(true)
    }
    hydrateConversations()
    return () => { cancelled = true }
  }, [activateConversation])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const media = window.matchMedia('(min-width: 1024px)')
    const sync = () => setSidebarOpen(media.matches)
    sync()
    media.addEventListener?.('change', sync)
    return () => media.removeEventListener?.('change', sync)
  }, [])

  const checkBackend = useCallback(async () => {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 15000)
      const res = await fetch('/api/health', { signal: controller.signal })
      clearTimeout(timeout)
      if (!res.ok) throw new Error(`Health check returned ${res.status}`)
      const data = await res.json()
      setBackendStatus({
        state: data.gemini_configured ? 'online' : 'needs_config',
        label: data.gemini_configured ? 'Backend online' : 'Backend online, Vertex not configured',
        detail: data.gemini_configured
          ? `FastAPI + Vertex project detected (${data.data_source || 'unknown data'})`
          : 'Set GOOGLE_CLOUD_PROJECT before chat',
      })
    } catch (err) {
      setBackendStatus({
        state: 'offline',
        label: 'Backend offline',
        detail: err.name === 'AbortError' ? 'Health check timed out' : 'Cannot reach port 8000',
      })
    }
  }, [])

  const fetchRules = useCallback(async () => {
    try {
      const res = await fetch('/api/rules')
      if (!res.ok) return
      const data = await res.json()
      setRules(data.rules || [])
    } catch {}
  }, [])
  const fetchRuleTemplates = useCallback(async () => {
    try {
      const res = await fetch('/api/rules/templates')
      if (!res.ok) return
      const data = await res.json()
      setRuleTemplates(data.templates || [])
    } catch {}
  }, [])
  const fetchOpportunities = useCallback(async () => {
    try {
      const res = await fetch('/api/opportunities')
      if (!res.ok) return
      const data = await res.json()
      setOpportunities(data.opportunities || [])
    } catch {}
  }, [])
  useEffect(() => { checkBackend(); fetchRules(); fetchRuleTemplates(); fetchOpportunities() }, [checkBackend, fetchRules, fetchRuleTemplates, fetchOpportunities])
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, loading])
  useEffect(() => { if (hydrated) setComposerFocusToken((t) => t + 1) }, [hydrated])
  const refreshStats = () => { checkBackend(); fetchRules(); fetchOpportunities() }


  useEffect(() => {
    if (!hydrated || !conversationId || !sessionId || messages.length === 0) return undefined
    const title = buildTitle(messages)
    const updatedAt = messages.at(-1)?.timestamp || new Date().toISOString()
    const conversation = {
      id: conversationId,
      sessionId,
      title,
      messages,
      createdAt: conversationCreatedAt || messages[0]?.timestamp || updatedAt,
      updatedAt,
    }
    setConversations((prev) => {
      const summary = {
        id: conversation.id,
        sessionId: conversation.sessionId,
        title,
        createdAt: conversation.createdAt,
        updatedAt,
        preview: messages.at(-1)?.text || messages.at(-1)?.cards?.[0]?.type || '',
        messageCount: messages.length,
        source: 'local',
      }
      return [summary, ...prev.filter((item) => item.id !== conversation.id)]
        .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
    })
    setPersistence((prev) => ({ ...prev, state: 'saving', detail: 'Saving conversation' }))
    let cancelled = false
    saveConversation(conversation).then((result) => {
      if (cancelled) return
      if (result.conversation?.id && result.conversation.id !== conversationId) {
        setConversationId(result.conversation.id)
        setSessionId(result.conversation.sessionId || result.conversation.id)
        setLastConversationId(result.conversation.id)
      }
      setPersistence({
        state: result.source === 'backend' ? 'synced' : 'local',
        source: result.source,
        detail: result.source === 'backend' ? 'Conversation saved' : 'Saved locally until backend persistence is ready',
      })
    })
    return () => { cancelled = true }
  }, [conversationCreatedAt, conversationId, hydrated, messages, sessionId])

  const startNewConversation = useCallback(() => {
    userStartedConversationRef.current = true
    const conversation = makeConversation()
    activateConversation(conversation)
    setPersistence((prev) => ({ ...prev, state: 'local', detail: 'Draft started locally' }))
    setInput('')
    setComposerFocusToken((value) => value + 1)
    if (typeof window !== 'undefined' && !window.matchMedia('(min-width: 1024px)').matches) setSidebarOpen(false)
  }, [activateConversation])

  const selectConversation = useCallback(async (id) => {
    // Immediately highlight the row and clear stale messages
    setConversationId(id)
    setConversationLoading(true)
    setMessages([])
    try {
      const conversation = await loadConversation(id)
      if (conversation) {
        activateConversation(conversation)
        setInput('')
        if (typeof window !== 'undefined' && !window.matchMedia('(min-width: 1024px)').matches) setSidebarOpen(false)
      }
    } finally {
      setConversationLoading(false)
      setComposerFocusToken((t) => t + 1)
    }
  }, [activateConversation])

  const removeConversation = useCallback(async (id) => {
    setDeletingId(id)
    try {
      await deleteConversation(id)
      const next = conversations.filter((conversation) => conversation.id !== id)
      setConversations(next)
      if (id === conversationId) {
        const replacement = next[0] ? await loadConversation(next[0].id) : makeConversation()
        activateConversation(replacement || makeConversation())
      }
    } finally {
      setDeletingId(null)
    }
  }, [activateConversation, conversationId, conversations])

  const removeRule = useCallback(async (id) => {
    setDeletingRuleId(id)
    try {
      const res = await fetch(`/api/rules/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`Rule delete failed with ${res.status}`)
      setRules((prev) => prev.filter((rule) => rule.id !== id))
      fetchRules()
    } catch {
      fetchRules()
    } finally {
      setDeletingRuleId(null)
    }
  }, [fetchRules])

  const removeOpportunity = useCallback(async (id) => {
    setDeletingOpportunityId(id)
    try {
      const res = await fetch(`/api/opportunities/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`Gap delete failed with ${res.status}`)
      setOpportunities((prev) => prev.filter((opportunity) => opportunity.id !== id))
      fetchOpportunities()
    } catch {
      fetchOpportunities()
    } finally {
      setDeletingOpportunityId(null)
    }
  }, [fetchOpportunities])

  const setBackendErrorState = (err) => {
    if (err.name === 'AbortError') {
      setBackendStatus({ state: 'slow', label: 'Backend slow', detail: 'The request timed out' })
    } else if (err.status === 503 || /credential|application-default|vertex/i.test(err.message || '')) {
      setBackendStatus({ state: 'auth', label: 'Vertex auth needs refresh', detail: 'Run gcloud auth application-default login' })
    } else if (err.name === 'TypeError' || err.message === 'Failed to fetch') {
      setBackendStatus({ state: 'offline', label: 'Backend offline', detail: 'Cannot reach port 8000' })
    } else if (err.status >= 500) {
      setBackendStatus({ state: 'error', label: 'Backend error', detail: err.message })
    }
  }

  const assetColumnsForRows = (rows) => {
    const preferred = [
      ['text', 'Container'],
      ['container_id', 'Container'],
      ['facility', 'Facility'],
      ['location', 'Location'],
      ['status_code', 'Status'],
      ['heading', 'Heading'],
      ['created_at', 'Detected at'],
      ['datetime', 'Detected at'],
      ['asset_id', 'Asset ID'],
      ['id', 'ID'],
    ]
    const keys = rows.slice(0, 10).flatMap((row) => row && typeof row === 'object' && !Array.isArray(row) ? Object.keys(row) : [])
    const seen = new Set()
    const columns = preferred
      .filter(([key]) => keys.includes(key) && !seen.has(key) && seen.add(key))
      .map(([key, label]) => ({ key, label }))
    for (const key of keys) {
      if (seen.has(key) || key === 'raw_payload') continue
      const value = rows.find((row) => row && typeof row === 'object' && Object.hasOwn(row, key))?.[key]
      if (value && typeof value === 'object') continue
      columns.push({ key, label: key.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase()) })
      seen.add(key)
      if (columns.length >= 10) break
    }
    return columns
  }

  const assetRowsToVisualization = ({ title, datasetName, rows, answer, visualizations, extra = {} }) => ({
    title,
    answer,
    datasets: [{
      name: datasetName,
      label: title,
      entity_type: 'asset',
      columns: assetColumnsForRows(rows),
      rows,
      count: rows.length,
    }],
    visualizations,
    provenance: {
      resource: datasetName,
      returned: rows.length,
    },
    ...extra,
  })

  const timelineToCard = (parsed) => {
    const rows = Array.isArray(parsed?.timeline) ? parsed.timeline : []
    if (!rows.length) return null
    const containerId = parsed.container_id || rows[0]?.container_id || rows[0]?.text || 'container'
    return {
      type: 'generic_visualization',
      data: assetRowsToVisualization({
        title: `Timeline for ${containerId}`,
        datasetName: 'asset_timeline',
        rows,
        answer: parsed.answer || `Found ${rows.length} timeline record${rows.length === 1 ? '' : 's'}.`,
        visualizations: [
          { type: 'timeline', dataset: 'asset_timeline', title: 'Detection timeline' },
          { type: 'image_gallery', dataset: 'asset_timeline', title: 'Detection images' },
          { type: 'video_gallery', dataset: 'asset_timeline', title: 'Related videos' },
          { type: 'table', dataset: 'asset_timeline', title: 'Timeline records' },
        ],
        extra: { container_id: parsed.container_id, count: rows.length, timeline: rows },
      }),
    }
  }

  const assetArrayToCard = (rows) => {
    const assetRows = rows.filter((row) => row && typeof row === 'object' && !Array.isArray(row))
    if (!assetRows.length) return null
    return {
      type: 'generic_visualization',
      data: assetRowsToVisualization({
        title: 'Asset records',
        datasetName: 'assets',
        rows: assetRows,
        answer: `Found ${assetRows.length} asset record${assetRows.length === 1 ? '' : 's'}.`,
        visualizations: [
          { type: 'table', dataset: 'assets', title: 'Asset records' },
          { type: 'image_gallery', dataset: 'assets', title: 'Asset images' },
        ],
      }),
    }
  }

  const parseNestedToolResult = (value, depth = 0) => {
    if (depth > 4 || value == null) return null
    if (typeof value === 'string') {
      try {
        return parseNestedToolResult(JSON.parse(value), depth + 1)
      } catch {
        return null
      }
    }
    if (Array.isArray(value)) return value
    if (typeof value !== 'object') return null
    if (Object.hasOwn(value, 'result')) return parseNestedToolResult(value.result, depth + 1)
    if (Array.isArray(value.content)) {
      const text = value.content
        .map((item) => typeof item?.text === 'string' ? item.text : '')
        .filter(Boolean)
        .join('\n')
      if (text) return parseNestedToolResult(text, depth + 1)
    }
    if (typeof value.text === 'string' && Object.keys(value).length <= 2) {
      return parseNestedToolResult(value.text, depth + 1)
    }
    return value
  }

  const parseToolCallsToCards = (toolCalls) => {
    if (!toolCalls) return []
    return toolCalls
      .filter((tc) => tc.result && typeof tc.result === 'string')
      .flatMap((tc) => {
        try {
          const parsed = parseNestedToolResult(tc.result)
          if (!parsed) return null
          if (Array.isArray(parsed)) return assetArrayToCard(parsed)
          if (Array.isArray(parsed?.timeline)) return timelineToCard(parsed)
          if (Array.isArray(parsed.datasets) && Array.isArray(parsed.visualizations)) return { type: 'generic_visualization', data: parsed }
          if (Object.hasOwn(parsed, 'resources') || Object.hasOwn(parsed, 'schema')) return { type: 'sitetrax_schema', data: parsed }
          // Rule / opportunity
          if (parsed.status === 'needs_confirmation' || parsed.action === 'create_monitoring_rule') return { type: 'approval_request', data: parsed }
          if (parsed.status === 'created' || parsed.rule_id) {
            // A rule may also carry a channel-gap (e.g. SMS requested but unsupported) —
            // surface both the rule card and the logged-opportunity card.
            const cards = [{ type: 'rule_created', data: parsed }]
            if (parsed.channel_gap) cards.push({ type: 'opportunity_logged', data: parsed.channel_gap })
            return cards
          }
          if (parsed.status === 'logged' || parsed.opportunity_id) return { type: 'opportunity_logged', data: parsed }
          // Container history
          if (Object.hasOwn(parsed, 'last_seen_location')) return { type: 'last_seen', data: parsed }
          if (Object.hasOwn(parsed, 'detection_count')) return { type: 'facility_activity', data: parsed }
          if (Object.hasOwn(parsed, 'time_since_last_seen')) return { type: 'dwell', data: parsed }
          if (Object.hasOwn(parsed, 'journey') && Array.isArray(parsed.journey)) return { type: 'asset_journey', data: parsed }
          // Facility last scan (facility_last_scan_tool)
          if (Object.hasOwn(parsed, 'last_container') && Object.hasOwn(parsed, 'scanned_ago')) return { type: 'facility_last_scan', data: { ...parsed, container_id: parsed.last_container, last_seen_location: parsed.facility, last_seen_time: parsed.scanned_at, last_seen_ago: parsed.scanned_ago } }
          // Yard / inventory
          if (Object.hasOwn(parsed, 'facility') && Object.hasOwn(parsed, 'assets') && Array.isArray(parsed.assets)) return { type: 'yard_inventory', data: parsed }
          if (Object.hasOwn(parsed, 'by_status') && typeof parsed.by_status === 'object') return { type: 'status_distribution', data: parsed }
          if (Object.hasOwn(parsed, 'containers') && Array.isArray(parsed.containers)) return { type: 'detention_list', data: parsed }
          if (Object.hasOwn(parsed, 'inbound_count') && Object.hasOwn(parsed, 'outbound_count')) return { type: 'inbound_outbound', data: parsed }
          // Company queries
          if (Object.hasOwn(parsed, 'company_prefix')) return { type: 'container_company', data: parsed }
          if (Object.hasOwn(parsed, 'company') && Object.hasOwn(parsed, 'total_scans')) return { type: 'company_activity', data: { ...parsed, company_prefix: parsed.company } }
          // Facility summaries / health
          if (Object.hasOwn(parsed, 'summary') && Object.hasOwn(parsed.summary, 'total_containers_7d')) return { type: 'facility_summary', data: parsed }
          if (parsed.status === 'health_check' && parsed.report) return { type: 'health_check', data: parsed }
          // Comparison
          if (Object.hasOwn(parsed, 'facility_a') && Object.hasOwn(parsed, 'facility_b')) return { type: 'compare_facilities', data: parsed }
          // Media
          if ((Object.hasOwn(parsed, 'image_url') || Object.hasOwn(parsed, 'asset_image')) && (Object.hasOwn(parsed, 'asset_id') || Object.hasOwn(parsed, 'id') || Object.hasOwn(parsed, 'container_id'))) return { type: 'image', data: parsed }
          if (Object.hasOwn(parsed, 'images') && Array.isArray(parsed.images) && parsed.images.length > 1) return { type: 'image_gallery', data: parsed }
          if (Object.hasOwn(parsed, 'url') && Object.hasOwn(parsed, 'video_id')) return { type: 'video', data: parsed }
          if (Object.hasOwn(parsed, 'videos') && Array.isArray(parsed.videos) && parsed.videos.length > 1) return { type: 'video_gallery', data: parsed }
          if (Object.hasOwn(parsed, 'facility') && Object.hasOwn(parsed, 'summary')) return { type: 'overview', data: parsed }
          if (Object.hasOwn(parsed, 'images') && Array.isArray(parsed.images)) return { type: 'image_list', data: parsed }
          if (Object.hasOwn(parsed, 'videos') && Array.isArray(parsed.videos)) return { type: 'video_list', data: parsed }
          // Rules / review
          if (Object.hasOwn(parsed, 'alerts') && Array.isArray(parsed.alerts)) return { type: 'rule_history', data: parsed }
          if (Object.hasOwn(parsed, 'needs_review_count')) return { type: 'review_queue', data: parsed }
          // Exception lists
          if (Object.hasOwn(parsed, 'containers_with_turnaround')) return { type: 'turnaround_time', data: parsed }
          if (Object.hasOwn(parsed, 'missing_count')) return { type: 'missing_containers', data: parsed }
          if (Object.hasOwn(parsed, 'camera_count')) return { type: 'camera_health', data: parsed }
          if (Object.hasOwn(parsed, 'duplicate_count')) return { type: 'duplicate_scans', data: parsed }
          if (Object.hasOwn(parsed, 'chassis') && Array.isArray(parsed.chassis)) return { type: 'chassis_activity', data: parsed }
          // Reports / export
          if (parsed.status === 'generated' && parsed.report) return { type: 'facility_report', data: parsed }
          if (parsed.status === 'exported' && parsed.csv_data) return { type: 'csv_export', data: parsed }
          // Metrics
          if (Object.hasOwn(parsed, 'by_day') && Object.hasOwn(parsed, 'total_containers')) return { type: 'metrics', data: parsed }
          // Search results
          if (Object.hasOwn(parsed, 'query') && Object.hasOwn(parsed, 'assets') && Array.isArray(parsed.assets)) return { type: 'search_results', data: parsed }
          // Facilities list
          if (Object.hasOwn(parsed, 'facilities') && Array.isArray(parsed.facilities)) return { type: 'facilities_list', data: parsed }
          // Reference / docs
          if (Object.hasOwn(parsed, 'matches') && Array.isArray(parsed.matches)) return { type: 'reference', data: parsed }
          // Preferences
          if (parsed.status === 'saved' && Object.hasOwn(parsed, 'preferences')) return { type: 'preferences', data: parsed }
          if (Object.hasOwn(parsed, 'preferences') && Object.hasOwn(parsed, 'session_id')) return { type: 'preferences', data: parsed }
        } catch {}
        return null
      })
      .filter(Boolean)
  }

  const applyOptimisticUpdatesFromCards = (cards) => {
    if (!cards || !cards.length) return
    const createdRules = cards
      .filter((c) => c.type === 'rule_created')
      .map((c) => {
        const data = c.data || {}
        const template = ruleTemplates.find((t) => t.display_name === data.template)
        return {
          id: data.rule_id,
          template: template?.id || data.template,
          display_name: data.template,
          description: template?.description || '',
          trigger_description: template?.trigger_description || '',
          action_description: template?.action_description || '',
          params: data.params || {},
          recipient_email: data.params?.email || '',
          created_at: new Date().toISOString(),
          evaluation_count: 0,
        }
      })
      .filter((r) => r.id)
    if (createdRules.length > 0) {
      setRules((prev) => {
        const existingIds = new Set(prev.map((r) => r.id))
        const newRules = createdRules.filter((r) => !existingIds.has(r.id))
        return [...newRules, ...prev]
      })
    }
    const createdOpportunities = cards
      .filter((c) => c.type === 'opportunity_logged')
      .map((c) => {
        const data = c.data || {}
        return {
          id: data.opportunity_id,
          user_request: data.user_request || data.message || '',
          reason: data.reason || '',
          category: data.category || '',
          created_at: new Date().toISOString(),
        }
      })
      .filter((o) => o.id)
    if (createdOpportunities.length > 0) {
      setOpportunities((prev) => {
        const existingIds = new Set(prev.map((o) => o.id))
        const newOpps = createdOpportunities.filter((o) => !existingIds.has(o.id))
        return [...newOpps, ...prev]
      })
    }
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim() || !sessionId) return
    if (loading) {
      const text = input.trim()
      setQueuedMessage(text)
      setInput('')
      return
    }
    const text = input.trim()
    const requestHistory = messages.slice(-8).map((msg) => ({
      role: msg.role,
      text: msg.text,
      cards: msg.cards,
    }))
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', text, cards: [], timestamp: new Date().toISOString() }])
    setInput('')
    setLoading(true)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 30000)
      const res = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId, history: requestHistory }), signal: controller.signal,
      })
      clearTimeout(timeout)
      if (!res.ok) {
        let errText = 'Something went wrong on the server.'
        try { const errData = await res.json(); errText = errData.detail || errText } catch {}
        const error = new Error(errText)
        error.status = res.status
        throw error
      }

      const agentMsgId = crypto.randomUUID()
      setMessages((prev) => [...prev, { id: agentMsgId, role: 'agent', text: '', cards: [], timestamp: new Date().toISOString() }])

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let toolResults = []
      let fullText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          buffer += decoder.decode()
          break
        }
        buffer += decoder.decode(value, { stream: true })

        const events = buffer.split('\n\n')
        buffer = events.pop()

        for (const eventStr of events) {
          if (!eventStr.trim()) continue
          const lines = eventStr.split('\n')
          let eventType = ''
          let eventData = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim()
            if (line.startsWith('data: ')) eventData = line.slice(6).trim()
          }
          if (!eventType || !eventData) continue

          const data = JSON.parse(eventData)

          if (eventType === 'text') {
            fullText += data
            setToolInProgress(null)
            setMessages((prev) => prev.map((m) => m.id === agentMsgId ? { ...m, text: fullText } : m))
          } else if (eventType === 'tool_call') {
            toolResults.push(data)
            setToolInProgress(data.name || null)
          } else if (eventType === 'tool_result') {
            const last = toolResults.findLast((t) => t.name === data.name && !t.result)
            if (last) last.result = data.result
            setToolInProgress(null)
          } else if (eventType === 'tool_progress') {
            const progressLabel = data.label || data.progress?.label
            const pages = data.pagination?.pages_fetched
            const rows = data.pagination?.rows_returned
            const fallback = pages ? `Fetched ${rows ?? 0} rows across ${pages} page${pages === 1 ? '' : 's'}…` : null
            setToolInProgress(progressLabel || fallback || data.name || 'Fetching paginated data…')
          } else if (eventType === 'done') {
            fullText = data.text || fullText
            toolResults = data.tool_results || toolResults
            const cards = parseToolCallsToCards(toolResults)
            applyOptimisticUpdatesFromCards(cards)
            setMessages((prev) => prev.map((m) => m.id === agentMsgId ? { ...m, text: fullText, cards } : m))
            setBackendStatus({ state: 'online', label: 'Backend online', detail: 'Chat completed' })
            refreshStats()
          } else if (eventType === 'error') {
            throw new Error(data.detail || 'Server error')
          }
        }
      }
      // Process any trailing event left in buffer after stream closes
      if (buffer.trim()) {
        const lines = buffer.split('\n')
        let eventType = ''
        let eventData = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim()
          if (line.startsWith('data: ')) eventData = line.slice(6).trim()
        }
        if (eventType && eventData) {
          const data = JSON.parse(eventData)
          if (eventType === 'done') {
            fullText = data.text || fullText
            toolResults = data.tool_results || toolResults
            const cards = parseToolCallsToCards(toolResults)
            applyOptimisticUpdatesFromCards(cards)
            setMessages((prev) => prev.map((m) => m.id === agentMsgId ? { ...m, text: fullText, cards } : m))
            setBackendStatus({ state: 'online', label: 'Backend online', detail: 'Chat completed' })
            refreshStats()
          } else if (eventType === 'error') {
            throw new Error(data.detail || 'Server error')
          }
        }
      }
    } catch (err) {
      setBackendErrorState(err)
      let msg = 'Sorry, something went wrong.'
      if (err.name === 'AbortError') msg = 'Request timed out. The agent is taking too long to respond.'
      else if (err.name === 'TypeError' || err.message === 'Failed to fetch') msg = 'Cannot reach the backend. Is it running on port 8000?'
      else if (err.message && err.message !== 'Server error') msg = err.message
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'agent', text: msg, cards: [], timestamp: new Date().toISOString() }])
    } finally {
      setLoading(false)
      setToolInProgress(null)
      setComposerFocusToken((t) => t + 1)
      // Auto-send queued message after current response finishes
      setTimeout(() => {
        setQueuedMessage((current) => {
          if (current && sendMessageRef.current) {
            setInput(current)
            setTimeout(() => sendMessageRef.current({ preventDefault: () => {} }), 0)
            return ''
          }
          return current
        })
      }, 50)
    }
  }

  useEffect(() => { sendMessageRef.current = sendMessage }, [sendMessage])

  useEffect(() => {
    const handler = (e) => {
      const { approved, template, params } = e.detail || {}
      if (approved) {
        setInput(`Yes, confirm creating the ${template || 'monitoring'} rule.`)
        requestAnimationFrame(() => {
          sendMessageRef.current?.({ preventDefault: () => {} })
        })
      } else {
        setInput('No, cancel that.')
        requestAnimationFrame(() => {
          sendMessageRef.current?.({ preventDefault: () => {} })
        })
      }
    }
    window.addEventListener('approval-response', handler)
    return () => window.removeEventListener('approval-response', handler)
  }, [])

  useEffect(() => {
    const handler = (event) => {
      const containerId = event.detail?.containerId
      if (!containerId) return
      setInput(`Show me all videos for container ${containerId}.`)
      requestAnimationFrame(() => {
        sendMessageRef.current?.({ preventDefault: () => {} })
      })
    }
    window.addEventListener('video-gallery-request', handler)
    return () => window.removeEventListener('video-gallery-request', handler)
  }, [])

  useEffect(() => {
    const handler = (event) => {
      const containerId = event.detail?.containerId
      if (!containerId) return
      setInput(`Show me all images for container ${containerId}.`)
      requestAnimationFrame(() => {
        sendMessageRef.current?.({ preventDefault: () => {} })
      })
    }
    window.addEventListener('image-gallery-request', handler)
    return () => window.removeEventListener('image-gallery-request', handler)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handler = (event) => {
      const { query, facility, hoursBack } = event.detail || {}
      if (!query && !facility) return
      const parts = []
      if (query) parts.push(`for ${query}`)
      if (facility) parts.push(`at ${facility}`)
      if (hoursBack) parts.push(`in the last ${hoursBack} hours`)
      setInput(`Show me all images ${parts.join(' ')}.`)
      requestAnimationFrame(() => {
        sendMessageRef.current?.({ preventDefault: () => {} })
      })
    }
    window.addEventListener('image-search-request', handler)
    return () => window.removeEventListener('image-search-request', handler)
  }, [])

  const simulateEvent = async (rule) => {
    const containerId = rule.params.container_id || 'TRDU1930583'
    const location = rule.params.location || 'Utah Intermodal Ramp'
    const isDwell = rule.template === 'dwell_time'
    setSimulating(true)
    try {
      const payload = { container_id: containerId, location, rule_id: rule.id }
      if (isDwell) payload.dwell_hours = Number(rule.params.threshold_hours || 0) + 1
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 15000)
      const res = await fetch('/api/simulate-event', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload), signal: controller.signal,
      })
      clearTimeout(timeout)
      if (!res.ok) {
        let errText = 'Event evaluation failed on the server.'
        try { const errData = await res.json(); errText = errData.detail || errText } catch {}
        const error = new Error(errText)
        error.status = res.status
        throw error
      }
      const data = await res.json()
      setBackendStatus({ state: 'online', label: 'Backend online', detail: 'Simulation completed' })
      if (data.alerts_fired > 0) {
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'agent', text: '', cards: [{ type: 'alert_fired', data: { event: data.event, alerts: data.alerts } }], timestamp: new Date().toISOString() }])
      } else {
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'agent', text: `${isDwell ? 'Dwell check' : 'Arrival'}: ${containerId} at ${location}. No matching rules triggered.`, cards: [], timestamp: new Date().toISOString() }])
      }
    } catch (err) {
      setBackendErrorState(err)
      let msg = 'Simulation failed.'
      if (err.name === 'AbortError') msg = 'Simulation timed out. Please try again.'
      else if (err.name === 'TypeError' || err.message === 'Failed to fetch') msg = 'Cannot reach the backend. Is it running on port 8000?'
      else if (err.message && err.message !== 'Server error') msg = err.message
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'agent', text: msg, cards: [], timestamp: new Date().toISOString() }])
    } finally { setSimulating(false) }
  }

  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-stone-50 text-stone-950 dark:bg-stone-950 dark:text-stone-50">
      <AppBackground />
      <Header
        rules={rules} opportunities={opportunities} messagesLength={messages.length}
        backendStatus={backendStatus}
        persistence={persistence}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        onNewConversation={startNewConversation}
        onClearChat={startNewConversation}
      />
      <div className="relative z-10 flex flex-1 overflow-hidden">
        {sidebarOpen && (
          <button
            type="button"
            aria-label="Close sidebar overlay"
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-x-0 bottom-0 top-[68px] z-20 bg-white/35 backdrop-blur-lg dark:bg-stone-950/45 lg:hidden"
            title="Close sidebar overlay"
          />
        )}
        <Sidebar
          open={sidebarOpen}
          rules={rules}
          ruleTemplates={ruleTemplates}
          opportunities={opportunities}
          conversations={conversations}
          activeConversationId={conversationId}
          persistence={persistence}
          hydrated={hydrated}
          deletingId={deletingId}
          deletingRuleId={deletingRuleId}
          deletingOpportunityId={deletingOpportunityId}
          onSelectConversation={selectConversation}
          onDeleteConversation={removeConversation}
          onDeleteRule={removeRule}
          onDeleteOpportunity={removeOpportunity}
          onSimulate={simulateEvent}
          onClose={() => setSidebarOpen(false)}
        />
        <main className="flex-1 flex flex-col min-w-0">
          <ChatMessages messages={messages} loading={loading} toolInProgress={toolInProgress} conversationLoading={conversationLoading} chatEndRef={chatEndRef} onSuggestionClick={(text) => setInput(text)} />
          <SimulateBar rules={rules} simulating={simulating} onSimulate={simulateEvent} />
          <ChatInput value={input} onChange={(e) => setInput(e.target.value)} onSubmit={sendMessage} loading={loading} focusToken={composerFocusToken} queued={!!queuedMessage} />
        </main>
      </div>
    </div>
  )
}

export default App
