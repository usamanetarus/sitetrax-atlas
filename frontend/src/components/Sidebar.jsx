import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import IconTooltipButton from './IconTooltipButton'
import {
  BellRinging,
  ChatsCircle,
  Clock,
  Lightbulb,
  MagnifyingGlass,
  SidebarSimple,
  Timer,
  Trash,
  Truck,
} from './Icons'

function formatTime(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

function formatTemplateLabel(template) {
  return String(template || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function getRuleIcon(template) {
  if (template === 'dwell_time') return Timer
  if (template === 'status_change') return Lightbulb
  if (template === 'facility_departure') return Truck
  if (template === 'low_confidence') return BellRinging
  if (template === 'review_queue') return BellRinging
  if (template === 'camera_offline') return BellRinging
  return Truck
}

function ConversationRow({ conversation, active, deleting, onSelect, onDelete }) {
  return (
        <div
      className={`group flex h-20 w-full rounded-lg border p-3 text-left transition-colors ${
          deleting
          ? 'border-red-200 bg-red-50/60 opacity-50 dark:border-red-400/20 dark:bg-red-500/5'
          : active
          ? 'border-stone-300 bg-stone-100 text-stone-950 shadow-sm shadow-stone-950/[0.04] dark:border-stone-700 dark:bg-stone-800/95 dark:text-stone-50 dark:shadow-black/25'
          : 'border-stone-200 bg-white text-stone-700 hover:border-stone-300 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:hover:border-stone-700'
      }`}
    >
      <div className="flex min-w-0 flex-1 items-start gap-2">
        <ChatsCircle size={16} weight="duotone" className={active ? 'mt-0.5 text-stone-700 dark:text-stone-200' : 'mt-0.5 text-stone-400 dark:text-stone-400'} />
        <button type="button" onClick={() => !deleting && onSelect(conversation.id)} className="min-w-0 flex-1 text-left" disabled={deleting}>
          <div className="truncate text-sm font-semibold">{conversation.title}</div>
          <div className="mt-0.5 flex items-center gap-1 text-[11px] text-stone-400 dark:text-stone-400">
            <Clock size={12} weight="duotone" />
            {deleting ? 'Deleting…' : formatTime(conversation.updatedAt)}
          </div>
          <div className="mt-1 truncate text-xs leading-5 text-stone-500 dark:text-stone-300">
            {conversation.preview || (conversation.messageCount > 0 ? `${conversation.messageCount} messages` : 'Ready for a new question')}
          </div>
        </button>
        {!deleting && (
          <IconTooltipButton
            type="button"
            onClick={(event) => { event.stopPropagation(); onDelete(conversation.id) }}
            className="rounded-md p-1 text-stone-300 opacity-0 transition-colors hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 dark:hover:bg-red-500/10 dark:hover:text-red-300"
            aria-label="Delete conversation"
            tooltip="Delete conversation"
            placement="left"
          >
            <Trash size={14} weight="duotone" />
          </IconTooltipButton>
        )}
      </div>
    </div>
  )
}

function RuleRow({ rule, deleting, onSimulate, onDelete }) {
  const Icon = getRuleIcon(rule.template)
  const label = rule.display_name || formatTemplateLabel(rule.template)
  const trigger = rule.trigger_description || rule.description || ''
  const destinationEmail = rule.recipient_email || rule.params?.email || ''
  return (
    <div className={`group rounded-lg border p-3 transition-colors ${
      deleting
        ? 'border-red-200 bg-red-50/70 opacity-60 dark:border-red-400/20 dark:bg-red-500/10'
        : 'border-stone-200 bg-white dark:border-stone-700 dark:bg-stone-900'
    }`}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon size={15} weight="duotone" className="shrink-0 text-stone-500" />
          <span className="truncate text-xs font-semibold text-stone-700 dark:text-stone-200">{label}</span>
        </div>
        {!deleting && (
          <IconTooltipButton
            type="button"
            onClick={(event) => { event.stopPropagation(); onDelete(rule.id) }}
            className="rounded-md p-1 text-stone-300 opacity-0 transition-colors hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 dark:hover:bg-red-500/10 dark:hover:text-red-300"
            aria-label="Delete rule"
            tooltip="Delete rule"
            placement="left"
          >
            <Trash size={14} weight="duotone" />
          </IconTooltipButton>
        )}
      </div>
      <div className="truncate font-mono text-[11px] text-stone-500 dark:text-stone-300">
        {rule.params.container_id || rule.params.location || Object.values(rule.params)[0] || rule.id}
      </div>
      {trigger && <div className="mt-1 max-h-8 overflow-hidden text-[10px] leading-4 text-stone-400 dark:text-stone-400">{trigger}</div>}
      <div className="mt-1 truncate text-[10px] leading-4 text-stone-500 dark:text-stone-300">
        Destination email: <span className="font-mono">{destinationEmail || 'Not set'}</span>
      </div>
      <button
        type="button"
        onClick={() => !deleting && onSimulate(rule)}
        disabled={deleting}
        className="mt-2.5 rounded-md border border-stone-200 px-2 py-1 text-[11px] font-semibold text-stone-500 transition-colors hover:border-stone-300 hover:text-stone-900 dark:border-stone-800 dark:text-stone-300 dark:hover:border-stone-700 dark:hover:text-stone-100"
      >
        {deleting ? 'Deleting...' : 'Simulate'}
      </button>
    </div>
  )
}

function OpportunityRow({ opportunity, deleting, onDelete }) {
  return (
    <div className={`group rounded-lg border p-3 transition-colors ${
      deleting
        ? 'border-red-200 bg-red-50/70 opacity-60 dark:border-red-400/20 dark:bg-red-500/10'
        : 'border-stone-200 bg-white dark:border-stone-700 dark:bg-stone-900'
    }`}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="truncate text-xs font-semibold text-stone-700 dark:text-stone-200">{opportunity.category}</div>
        {!deleting && (
          <IconTooltipButton
            type="button"
            onClick={(event) => { event.stopPropagation(); onDelete(opportunity.id) }}
            className="rounded-md p-1 text-stone-300 opacity-0 transition-colors hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 dark:hover:bg-red-500/10 dark:hover:text-red-300"
            aria-label="Delete gap"
            tooltip="Delete gap"
            placement="left"
          >
            <Trash size={14} weight="duotone" />
          </IconTooltipButton>
        )}
      </div>
      <div className="truncate text-[11px] text-stone-500 dark:text-stone-300">{opportunity.user_request}</div>
      {deleting && <div className="mt-1 text-[10px] font-medium text-red-500 dark:text-red-300">Deleting...</div>}
    </div>
  )
}

function ConversationSkeleton() {
  return (
    <div className="flex h-20 w-full animate-pulse rounded-lg border border-stone-200 bg-white p-3 dark:border-stone-800 dark:bg-stone-950">
      <div className="flex w-full flex-col gap-2">
        <div className="h-3 w-3/4 rounded bg-stone-200 dark:bg-stone-700" />
        <div className="h-2.5 w-1/3 rounded bg-stone-100 dark:bg-stone-800" />
        <div className="h-2.5 w-5/6 rounded bg-stone-100 dark:bg-stone-800" />
      </div>
    </div>
  )
}

function TabButton({ active, onClick, icon: Icon, label, count }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-semibold transition-colors ${
          active
          ? 'bg-stone-200 text-stone-950 shadow-sm shadow-stone-950/10 ring-1 ring-stone-300/40  dark:bg-stone-800 dark:text-stone-50 dark:shadow-stone-950/30 dark:ring-stone-600/30'
          : 'text-stone-500 hover:text-stone-700 dark:text-stone-300 dark:hover:text-stone-200'
      }`}
    >
      <Icon size={13} weight="duotone" />
      {label}
      <span className={`ml-0.5 rounded-full px-1.5 py-0 text-[10px] ${
        active ? 'bg-stone-300 text-stone-800 dark:bg-stone-700 dark:text-stone-50' : 'bg-stone-200/60 text-stone-500 dark:bg-stone-800 dark:text-stone-300'
      }`}>
        {count}
      </span>
    </button>
  )
}

function SidebarContent({
  conversations,
  visibleConversations,
  activeConversationId,
  conversationSearch,
  setConversationSearch,
  persistence,
  hydrated,
  deletingId,
  deletingRuleId,
  deletingOpportunityId,
  rules,
  ruleTemplates,
  opportunities,
  onSelectConversation,
  onDeleteConversation,
  onDeleteRule,
  onDeleteOpportunity,
  onSimulate,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState('chat')
  const [showRuleCatalog, setShowRuleCatalog] = useState(false)
  const hasRules = rules.length > 0
  const hasOpportunities = opportunities.length > 0

  return (
    <>

      <div className="flex min-h-0 flex-1 flex-col px-4 pb-5 pt-3">
        {/* Tab bar */}
        <div className="mb-3 flex w-full gap-1 overflow-hidden rounded-lg border border-stone-200 bg-stone-50 p-1 dark:border-stone-700 dark:bg-stone-900">
          <TabButton
            active={activeTab === 'chat'}
            onClick={() => setActiveTab('chat')}
            icon={ChatsCircle}
            label="Chat"
            count={conversations.length}
          />
          <TabButton
            active={activeTab === 'rules'}
            onClick={() => setActiveTab('rules')}
            icon={BellRinging}
            label="Rules"
            count={rules.length}
          />
          <TabButton
            active={activeTab === 'gaps'}
            onClick={() => setActiveTab('gaps')}
            icon={Lightbulb}
            label="Gaps"
            count={opportunities.length}
          />
        </div>

        {/* Scrollable content */}
        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-2 pb-1">
          {activeTab === 'chat' && (
            <div className="flex flex-col gap-2">
              <div className="relative">
                <MagnifyingGlass size={14} weight="duotone" className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-400" />
                <input
                  type="text"
                  value={conversationSearch}
                  onChange={(e) => setConversationSearch(e.target.value)}
                  placeholder="Search conversations"
                className="h-9 w-full rounded-lg border border-stone-200 bg-white pl-8 pr-3 text-xs font-medium text-stone-700 outline-none transition-colors placeholder:text-stone-400 focus:border-stone-300 focus:ring-4 focus:ring-stone-500/10 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:placeholder:text-stone-500 dark:focus:border-stone-700"
                />
              </div>
              {!hydrated ? (
                <>
                  <ConversationSkeleton />
                  <ConversationSkeleton />
                  <ConversationSkeleton />
                </>
              ) : visibleConversations.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <ChatsCircle size={24} weight="duotone" className="mb-2 text-stone-300 dark:text-stone-600" />
                  <p className="text-xs font-medium text-stone-500 dark:text-stone-300">
                    {conversations.length === 0 ? 'No conversations yet' : 'No conversations match that search.'}
                  </p>
                  {conversations.length === 0 && (
                    <p className="mt-0.5 text-[11px] text-stone-400 dark:text-stone-400">Start a new chat to begin.</p>
                  )}
                </div>
              ) : (
                visibleConversations.map((conversation) => (
                  <ConversationRow
                    key={conversation.id}
                    conversation={conversation}
                    active={conversation.id === activeConversationId}
                    deleting={conversation.id === deletingId}
                    onSelect={onSelectConversation}
                    onDelete={onDeleteConversation}
                  />
                ))
              )}
            </div>
          )}

          {activeTab === 'rules' && (
            <div className="flex flex-col gap-2.5">
              {/*<button*/}
              {/*  type="button"*/}
              {/*  onClick={() => setShowRuleCatalog((value) => !value)}*/}
              {/*  className="flex items-center justify-between rounded-lg border border-stone-200 bg-white px-3 py-2 text-left text-xs font-semibold text-stone-700 transition-colors hover:border-stone-300 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:hover:border-stone-700"*/}
              {/*>*/}
              {/*  <span>Rule types</span>*/}
              {/*  <span className="text-[10px] font-medium text-stone-400 dark:text-stone-400">{ruleTemplates?.length || 0} available</span>*/}
              {/*</button>*/}
              <AnimatePresence initial={false}>
                {showRuleCatalog && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden rounded-lg border border-stone-200 bg-stone-50 dark:border-stone-800 dark:bg-stone-950"
                  >
                    <div className="p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-stone-400 dark:text-stone-500">
                        How they trigger
                      </div>
                      <div className="flex flex-col gap-2">
                        {(ruleTemplates || []).map((template) => (
                          <div key={template.id} className="rounded-md border border-stone-200 bg-white p-2 dark:border-stone-800 dark:bg-stone-950">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-xs font-semibold text-stone-800 dark:text-stone-100">{template.display_name}</div>
                              <div className="text-[10px] text-stone-400 dark:text-stone-500">{template.id}</div>
                            </div>
                            <div className="mt-0.5 text-[11px] leading-4 text-stone-500 dark:text-stone-300">{template.trigger_description}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {hasRules ? (
                <div className="space-y-2.5">
                  {rules.map((rule) => (
                    <RuleRow
                      key={rule.id}
                      rule={rule}
                      deleting={rule.id === deletingRuleId}
                      onSimulate={onSimulate}
                      onDelete={onDeleteRule}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <BellRinging size={24} weight="duotone" className="mb-2 text-stone-300 dark:text-stone-600" />
                  <p className="text-xs font-medium text-stone-500 dark:text-stone-300">No rules yet</p>
                  <p className="mt-0.5 text-[11px] text-stone-400 dark:text-stone-400">Ask the agent to monitor a container or dwell rule.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'gaps' && (
            hasOpportunities ? (
              <div className="space-y-2.5">
                {opportunities.map((opportunity) => (
                  <OpportunityRow
                    key={opportunity.id}
                    opportunity={opportunity}
                    deleting={opportunity.id === deletingOpportunityId}
                    onDelete={onDeleteOpportunity}
                  />
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <Lightbulb size={24} weight="duotone" className="mb-2 text-stone-300 dark:text-stone-600" />
                <p className="text-xs font-medium text-stone-500 dark:text-stone-300">No gaps yet</p>
                <p className="mt-0.5 text-[11px] text-stone-400 dark:text-stone-400">Ask the agent to find opportunities.</p>
              </div>
            )
          )}
        </div>
      </div>
    </>
  )
}

export default function Sidebar({
  open,
  rules,
  ruleTemplates,
  opportunities,
  conversations,
  activeConversationId,
  persistence,
  hydrated,
  deletingId,
  deletingRuleId,
  deletingOpportunityId,
  onSelectConversation,
  onDeleteConversation,
  onDeleteRule,
  onDeleteOpportunity,
  onSimulate,
  onClose,
}) {
  const [conversationSearch, setConversationSearch] = useState('')
  const query = conversationSearch.trim().toLowerCase()
  const visibleConversations = query
    ? conversations.filter((conversation) => (
        `${conversation.title || ''} ${conversation.preview || ''}`.toLowerCase().includes(query)
      ))
    : conversations

  return (
    <>
      <motion.aside
        initial={false}
        animate={{
          width: open ? 320 : 0,
          opacity: open ? 1 : 0,
          x: open ? 0 : -18,
        }}
        transition={{ type: 'spring', stiffness: 320, damping: 34, mass: 0.8 }}
        className="relative z-10 hidden h-full shrink-0 overflow-hidden border-r border-stone-200/70 bg-white dark:border-stone-700 dark:bg-stone-900 lg:flex"
        aria-hidden={!open}
      >
        <div className="flex h-full w-[320px] shrink-0 flex-col">
          <SidebarContent
            conversations={conversations}
            visibleConversations={visibleConversations}
            activeConversationId={activeConversationId}
            conversationSearch={conversationSearch}
            setConversationSearch={setConversationSearch}
            persistence={persistence}
            hydrated={hydrated}
            deletingId={deletingId}
            deletingRuleId={deletingRuleId}
            deletingOpportunityId={deletingOpportunityId}
            rules={rules}
            ruleTemplates={ruleTemplates}
            opportunities={opportunities}
            onSelectConversation={onSelectConversation}
            onDeleteConversation={onDeleteConversation}
            onDeleteRule={onDeleteRule}
            onDeleteOpportunity={onDeleteOpportunity}
            onSimulate={onSimulate}
          />
        </div>
      </motion.aside>

      <AnimatePresence>
        {open && (
          <motion.aside
            initial={{ x: -340, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -340, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 330, damping: 34, mass: 0.9 }}
            className="absolute inset-y-0 left-0 z-30 flex w-[320px] max-w-[88vw] flex-col border-r border-stone-200/70 bg-white dark:border-stone-700 dark:bg-stone-900 lg:hidden"
          >
            <SidebarContent
              conversations={conversations}
              visibleConversations={visibleConversations}
              activeConversationId={activeConversationId}
              conversationSearch={conversationSearch}
              setConversationSearch={setConversationSearch}
              persistence={persistence}
              hydrated={hydrated}
              deletingId={deletingId}
              deletingRuleId={deletingRuleId}
              deletingOpportunityId={deletingOpportunityId}
              rules={rules}
              ruleTemplates={ruleTemplates}
              opportunities={opportunities}
              onSelectConversation={onSelectConversation}
              onDeleteConversation={onDeleteConversation}
              onDeleteRule={onDeleteRule}
              onDeleteOpportunity={onDeleteOpportunity}
              onSimulate={onSimulate}
            />
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
