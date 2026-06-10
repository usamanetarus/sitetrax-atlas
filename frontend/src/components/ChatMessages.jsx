import { motion } from 'framer-motion'
import MessageBubble from './MessageBubble'
import { BellRinging, Lightbulb, MagnifyingGlass, Sparkle } from './Icons'
import ContainerGlobe from './ContainerGlobe'
import { containerMarkers } from '../data/containerMarkers'

const TOOL_LABELS = {
  query_assets_tool: 'Querying assets…',
  container_last_seen_tool: 'Looking up container…',
  container_facility_activity_tool: 'Counting detections…',
  container_dwell_tool: 'Calculating dwell…',
  facility_last_scan_tool: 'Finding last scan…',
  facility_recent_activity_tool: 'Loading recent activity…',
  list_facilities_tool: 'Listing facilities…',
  container_video_tool: 'Fetching video clip…',
  get_timeline_with_videos_tool: 'Building timeline…',
  search_videos_tool: 'Searching videos…',
  search_images_tool: 'Searching images…',
  facility_metrics_tool: 'Loading metrics…',
  yard_inventory_tool: 'Loading yard inventory…',
  status_distribution_tool: 'Analyzing status codes…',
  detention_list_tool: 'Checking detention risk…',
  inbound_outbound_tool: 'Analyzing gate traffic…',
  chassis_activity_tool: 'Querying chassis…',
  duplicate_detection_tool: 'Scanning for duplicates…',
  recent_activity_by_company_tool: 'Checking company activity…',
  get_user_preferences_tool: 'Loading preferences…',
  set_user_preferences_tool: 'Saving preferences…',
  facility_summary_tool: 'Building facility summary…',
  facility_health_check_tool: 'Running health check…',
  review_queue_tool: 'Checking review queue…',
  turnaround_time_tool: 'Calculating turnaround times…',
  missing_containers_tool: 'Searching for missing containers…',
  camera_health_tool: 'Checking cameras…',
  asset_journey_tool: 'Tracing container journey…',
  compare_facilities_tool: 'Comparing facilities…',
  rule_history_tool: 'Loading alert history…',
  create_monitoring_rule_tool: 'Creating rule…',
  export_to_csv_tool: 'Exporting to CSV…',
  generate_facility_report_tool: 'Generating report…',
  sitetrax_reference_tool: 'Searching documentation…',
  load_memory: 'Loading session memory…',
}

const suggestions = [
  { icon: MagnifyingGlass, label: 'Last seen', text: 'When was TRDU1930583 last seen?' },
  { icon: BellRinging, label: 'Facility activity', text: 'How many times has TRDU1930583 been at Utah Intermodal Ramp?' },
  { icon: Lightbulb, label: 'Dwell estimate', text: "What's the dwell for TRDU1930583?" },
]

function WelcomeScreen({ onSuggestionClick }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="flex min-h-full items-center justify-center px-4 py-8">
      <div className="relative grid w-full max-w-6xl overflow-hidden rounded-xl text-left
        bg-white ring-1 ring-stone-200 shadow-xl
        dark:bg-stone-950 dark:ring-stone-800 dark:shadow-black/60
        lg:min-h-[430px] lg:grid-cols-[0.84fr_1.16fr]">

        {/* Left content */}
        <div className="relative z-20 flex flex-col justify-center px-7 py-8 lg:px-11 lg:py-10">
          <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-stone-400 dark:text-stone-400">
            SiteTrax.io Atlas Agent
          </p>
          <h2 className="mb-4 text-3xl font-semibold leading-snug text-stone-950 dark:text-stone-50 sm:text-4xl">
            Track container intelligence<br className="hidden sm:block" /> from the gate to the globe.
          </h2>
          <p className="mb-8 max-w-sm text-sm leading-relaxed text-stone-500 dark:text-stone-300">
            Ask anything about your yards, containers, or facilities. Live SiteTrax data, answered in plain language.
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => {
              const Icon = s.icon
              return (
                <button key={s.text} type="button" onClick={() => onSuggestionClick(s.text)}
                  className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-transparent px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:border-stone-300 hover:text-stone-900
                    dark:border-stone-800 dark:text-stone-300 dark:hover:border-stone-700 dark:hover:text-stone-100">
                  <Icon size={15} weight="duotone" className="shrink-0" />
                  {s.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Right globe pane — h-full so it always fills the grid row */}
        <div className="relative z-10 h-full min-h-[210px] sm:min-h-[380px] lg:min-h-[430px]">
          <ContainerGlobe embedded markers={containerMarkers} />
        </div>
      </div>
    </motion.div>
  )
}

function TypingIndicator({ toolInProgress }) {
  const label = toolInProgress ? (TOOL_LABELS[toolInProgress] || toolInProgress || 'Working…') : null
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-stone-200 bg-white text-stone-500 shadow-sm dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200">
        <Sparkle size={16} weight="duotone" />
      </div>
      <div className="flex items-center gap-2.5 rounded-xl border border-stone-200 bg-white px-4 py-3 shadow-sm dark:border-stone-800 dark:bg-stone-950">
        <div className="flex gap-1">
          <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
        </div>
        {label && (
          <motion.span
            key={label}
            initial={{ opacity: 0, x: 4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
            className="text-xs text-stone-400 dark:text-stone-400"
          >
            {label}
          </motion.span>
        )}
      </div>
    </motion.div>
  )
}

function ConversationLoadingSkeleton() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 py-2">
      {[1, 2, 3].map((i) => (
        <div key={i} className={`flex gap-3 ${i % 2 === 0 ? 'flex-row-reverse' : ''}`}>
          <div className="h-8 w-8 shrink-0 animate-pulse rounded-lg bg-stone-200 dark:bg-stone-800" />
          <div className={`flex flex-col gap-2 ${i % 2 === 0 ? 'items-end' : 'items-start'}`} style={{ width: `${48 + i * 12}%` }}>
            <div className="h-10 w-full animate-pulse rounded-xl bg-stone-100 dark:bg-stone-800" style={{ animationDelay: `${i * 80}ms` }} />
            {i === 1 && <div className="h-16 w-full animate-pulse rounded-xl bg-stone-100 dark:bg-stone-800" style={{ animationDelay: '160ms' }} />}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function ChatMessages({ messages, loading, toolInProgress, conversationLoading, chatEndRef, onSuggestionClick }) {
  return (
    <div className="messages flex-1 overflow-y-auto px-4 py-6 sm:px-8 sm:py-8">
      {conversationLoading ? (
        <ConversationLoadingSkeleton />
      ) : messages.length === 0 ? (
        <WelcomeScreen onSuggestionClick={onSuggestionClick} />
      ) : (
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)}
          {loading && <TypingIndicator toolInProgress={toolInProgress} />}
          <div ref={chatEndRef} />
        </div>
      )}
    </div>
  )
}
