import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import RuleCard from './Cards/RuleCard'
import AlertCard from './Cards/AlertCard'
import OpportunityCard from './Cards/OpportunityCard'
import LastSeenCard from './Cards/LastSeenCard'
import FacilityActivityCard from './Cards/FacilityActivityCard'
import DwellCard from './Cards/DwellCard'
import YardInventoryCard from './Cards/YardInventoryCard'
import StatusDistributionCard from './Cards/StatusDistributionCard'
import DetentionCard from './Cards/DetentionCard'
import InboundOutboundCard from './Cards/InboundOutboundCard'
import ContainerCompanyCard from './Cards/ContainerCompanyCard'
import FacilitySummaryCard from './Cards/FacilitySummaryCard'
import AssetJourneyCard from './Cards/AssetJourneyCard'
import CompareFacilitiesCard from './Cards/CompareFacilitiesCard'
import VideoCard from './Cards/VideoCard'
import VideoGalleryCard from './Cards/VideoGalleryCard'
import ImageCard from './Cards/ImageCard'
import ImageGalleryCard from './Cards/ImageGalleryCard'
import OverviewCard from './Cards/OverviewCard'
import ApprovalCard from './Cards/ApprovalCard'
import ReviewQueueCard from './Cards/ReviewQueueCard'
import CameraHealthCard from './Cards/CameraHealthCard'
import FacilityHealthCheckCard from './Cards/FacilityHealthCheckCard'
import FacilityReportCard from './Cards/FacilityReportCard'
import CsvExportCard from './Cards/CsvExportCard'
import GenericDataCard from './Cards/GenericDataCard'
import GenericVisualizationCard from './Cards/GenericVisualizationCard'
import RuleHistoryCard from './Cards/RuleHistoryCard'
import ReferenceCard from './Cards/ReferenceCard'
import MetricsCard from './Cards/MetricsCard'
import SearchResultsCard from './Cards/SearchResultsCard'
import { Robot, User } from './Icons'

const cardComponents = {
  rule_created: RuleCard,
  alert_fired: AlertCard,
  opportunity_logged: OpportunityCard,
  last_seen: LastSeenCard,
  facility_last_scan: LastSeenCard,
  facility_activity: FacilityActivityCard,
  dwell: DwellCard,
  yard_inventory: YardInventoryCard,
  status_distribution: StatusDistributionCard,
  detention_list: DetentionCard,
  inbound_outbound: InboundOutboundCard,
  container_company: ContainerCompanyCard,
  facility_summary: FacilitySummaryCard,
  asset_journey: AssetJourneyCard,
  compare_facilities: CompareFacilitiesCard,
  video: VideoCard,
  image: ImageCard,
  rule_history: RuleHistoryCard,
  review_queue: ReviewQueueCard,
  turnaround_time: (props) => GenericDataCard({ title: 'Turnaround Time', data: props.data }),
  missing_containers: (props) => GenericDataCard({ title: 'Missing Containers', data: props.data }),
  camera_health: CameraHealthCard,
  facility_report: FacilityReportCard,
  csv_export: CsvExportCard,
  health_check: FacilityHealthCheckCard,
  reference: ReferenceCard,
  metrics: MetricsCard,
  search_results: SearchResultsCard,
  video_list: VideoGalleryCard,
  video_gallery: VideoGalleryCard,
  image_list: ImageGalleryCard,
  image_gallery: ImageGalleryCard,
  overview: OverviewCard,
  approval_request: ApprovalCard,
  facilities_list: (props) => GenericDataCard({ title: 'Facilities', data: props.data }),
  chassis_activity: (props) => GenericDataCard({ title: 'Chassis Activity', data: props.data }),
  duplicate_scans: (props) => GenericDataCard({ title: 'Duplicate Scans', data: props.data }),
  company_activity: ContainerCompanyCard,
  preferences: (props) => GenericDataCard({ title: 'Preferences', data: props.data }),
  generic_visualization: GenericVisualizationCard,
  sitetrax_schema: (props) => GenericDataCard({ title: 'SiteTrax Schema', data: props.data }),
}

function MarkdownMessage({ text, isUser }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold text-inherit">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1 last:mb-0">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1 last:mb-0">{children}</ol>,
        li: ({ children }) => <li className="pl-1">{children}</li>,
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className={isUser ? 'underline decoration-white/50 underline-offset-2' : 'text-stone-700 underline decoration-stone-300 underline-offset-2 dark:text-stone-200'}
          >
            {children}
          </a>
        ),
        code: ({ className, children }) => !className ? (
          <code className={isUser ? 'rounded bg-white/15 px-1 py-0.5 font-mono text-[0.9em]' : 'rounded bg-stone-100 px-1 py-0.5 font-mono text-[0.9em] text-stone-800 dark:bg-stone-800 dark:text-stone-100'}>
            {children}
          </code>
        ) : (
          <code className="block overflow-x-auto whitespace-pre rounded-lg bg-stone-950 p-3 font-mono text-xs leading-5 text-stone-100 dark:bg-stone-950/70">
            {children}
          </code>
        ),
        pre: ({ children }) => <pre className="my-2 max-w-full overflow-x-auto">{children}</pre>,
        blockquote: ({ children }) => (
          <blockquote className={isUser ? 'border-l-2 border-white/40 pl-3 opacity-90' : 'border-l-2 border-stone-300 pl-3 text-stone-600 dark:text-stone-200'}>
            {children}
          </blockquote>
        ),
        table: ({ children }) => <div className="my-2 overflow-x-auto"><table className="min-w-full border-collapse text-xs">{children}</table></div>,
        th: ({ children }) => <th className="border border-stone-200 px-2 py-1 text-left font-semibold dark:border-stone-800">{children}</th>,
        td: ({ children }) => <td className="border border-stone-200 px-2 py-1 dark:border-stone-800">{children}</td>,
      }}
    >
      {text}
    </ReactMarkdown>
  )
}

export default function MessageBubble({ msg }) {
  const isUser = msg.role === 'user'
  const ts = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      <div className={`flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg border shadow-sm ${isUser ? 'border-stone-700 bg-stone-900 text-white dark:border-stone-200 dark:bg-stone-100 dark:text-stone-950' : 'border-stone-200 bg-white text-stone-600 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200'}`}>
        {isUser ? <User size={16} weight="duotone" /> : <Robot size={16} weight="duotone" />}
      </div>
      <div className={`flex min-w-0 max-w-[86%] flex-col gap-2 sm:max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        {msg.text && (
          <div className={`px-4 py-2.5 text-[15px] leading-relaxed shadow-sm ${isUser ? 'rounded-xl rounded-br bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-950' : 'rounded-xl rounded-bl border border-stone-200 bg-white/90 text-stone-700 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200'}`}>
            <MarkdownMessage text={msg.text} isUser={isUser} />
          </div>
        )}
        {msg.cards.length > 0 && (
          <div className="flex w-full flex-col gap-2">
            {msg.cards.map((card, index) => {
              const Card = cardComponents[card.type]
              return Card ? <Card key={`${card.type}-${card.data?.rule_id || card.data?.opportunity_id || card.data?.event?.timestamp || card.data?.container_id || index}`} data={card.data} /> : null
            })}
          </div>
        )}
        <span className={`px-1 text-[10px] text-stone-400 dark:text-stone-400 ${isUser ? 'text-right' : ''}`}>{ts}</span>
      </div>
    </motion.div>
  )
}
