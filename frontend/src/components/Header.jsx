import { motion, AnimatePresence } from 'framer-motion'
import { useTheme } from '../ThemeContext'
import IconTooltipButton from './IconTooltipButton'
import {
  CloudCheck,
  CloudWarning,
  ChatsCircle,
  Moon,
  Plus,
  ArrowLineLeft,
  ArrowLineRight,
  SidebarSimple,
  Sun,
  XCircle,
} from './Icons'

const statusStyles = {
  online: 'bg-stone-500 shadow-stone-500/30',
  checking: 'bg-stone-400 shadow-stone-400/30',
  slow: 'bg-stone-500 shadow-stone-500/30',
  auth: 'bg-stone-500 shadow-stone-500/30',
  needs_config: 'bg-stone-500 shadow-stone-500/30',
  error: 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300',
  offline: 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300',
}

function StatusLine({ status, persistence }) {
  const Icon = status.state === 'online' ? CloudCheck : CloudWarning
  const isBad = ['error', 'offline'].includes(status.state)
  const savedLabel = persistence?.source === 'backend'
    ? 'Saved to Firestore'
    : persistence?.state === 'saving'
      ? 'Saving'
      : 'Local cache'

  return (
    <div className="hidden min-w-0 items-center gap-2 rounded-lg border border-stone-200 bg-white/75 px-2.5 py-1.5 text-xs text-stone-500 shadow-sm shadow-stone-950/[0.03] backdrop-blur-xl dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 md:inline-flex">
      <span
        className={`h-2 w-2 shrink-0 rounded-full shadow-lg ${isBad ? 'bg-red-500 shadow-red-500/30' : statusStyles[status.state] || statusStyles.checking}`}
        title={status.detail}
      />
      <Icon size={14} weight="duotone" className={isBad ? 'text-red-500 dark:text-red-300' : 'text-stone-600 dark:text-stone-200'} />
      <span className="truncate font-medium">{status.label}</span>
      <span className="h-3 w-px bg-stone-200 dark:bg-stone-800" />
      <ChatsCircle size={14} weight="duotone" className="text-stone-400 dark:text-stone-400" />
      <span className="truncate">{savedLabel}</span>
    </div>
  )
}

export default function Header({
  sidebarOpen,
  rules,
  opportunities,
  messagesLength,
  backendStatus,
  persistence,
  onToggleSidebar,
  onNewConversation,
  onClearChat,
}) {
  const { theme, toggle } = useTheme()

  return (
    <motion.header
      initial={false}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      className="relative z-20 grid min-h-[68px] grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-stone-200/70 bg-white/86 px-3 shadow-sm shadow-stone-950/5 backdrop-blur-xl dark:border-stone-800 dark:bg-stone-950 sm:px-4"
    >
      <div className="flex min-w-0 items-center gap-3">
        <IconTooltipButton
          tooltip={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          onClick={onToggleSidebar}
          whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.96 }}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-stone-200 bg-white text-stone-600 shadow-sm shadow-stone-950/5 transition-colors hover:border-stone-300 hover:text-stone-900 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:hover:border-stone-700 dark:hover:text-stone-100"
          aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        >
          <AnimatePresence mode="wait" initial={false}>
            {sidebarOpen ? (
              <motion.div
                key="close"
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 4 }}
                transition={{ duration: 0.15 }}
              >
                <ArrowLineLeft size={18} weight="duotone" />
              </motion.div>
            ) : (
              <motion.div
                key="open"
                initial={{ opacity: 0, x: 4 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -4 }}
                transition={{ duration: 0.15 }}
              >
                <ArrowLineRight size={18} weight="duotone" />
              </motion.div>
            )}
          </AnimatePresence>
        </IconTooltipButton>
        <div className="my-1.5 flex min-w-0 items-center gap-3 rounded-2xl border border-stone-200/80 bg-stone-100/90 px-3 py-2.5 shadow-sm shadow-stone-950/[0.03] dark:border-stone-800 dark:bg-stone-900/85">
          <motion.img
            src="/SiteTrax.io Full Color Logo.png" alt="SiteTrax.io"
            className="h-12 w-12 shrink-0 rounded-xl bg-white object-contain p-0.5 ring-1 ring-stone-200 dark:bg-stone-950 dark:ring-stone-800 sm:h-12 sm:w-12"
            whileHover={{ scale: 1.04, rotate: -1 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
          />
          <div className="min-w-0 pr-1">
            <h1 className="truncate text-lg font-semibold leading-5 text-stone-950 dark:text-stone-50 sm:text-xl">SiteTrax.io</h1>
            <p className="hidden text-xs font-medium text-stone-500 dark:text-stone-300 sm:block">Atlas Agent</p>
          </div>
        </div>
      </div>

      {/*<div className="flex min-w-0 justify-center">*/}
      {/*  <StatusLine status={backendStatus} persistence={persistence} />*/}
      {/*</div>*/}

      <div className="flex items-center justify-end gap-1.5 sm:gap-2">
        <button
          type="button"
          onClick={onNewConversation}
          className="inline-flex h-10 items-center gap-2 rounded-xl bg-stone-900 px-3 text-xs font-semibold text-stone-50 shadow-lg shadow-stone-950/15 transition-colors hover:bg-stone-800 disabled:opacity-60 dark:bg-stone-100 dark:text-stone-950 dark:hover:bg-white sm:px-4"
        >
          <Plus size={15} weight="bold" />
          <span className="hidden sm:inline">New chat</span>
        </button>

        <IconTooltipButton
          tooltip="Toggle theme"
          onClick={toggle}
          whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-stone-200 bg-white text-stone-600 shadow-sm shadow-stone-950/5 transition-colors hover:border-stone-300 hover:text-stone-900 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200 dark:hover:border-stone-700 dark:hover:text-stone-100"
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? <Sun size={18} weight="duotone" /> : <Moon size={18} weight="duotone" />}
        </IconTooltipButton>

        {messagesLength > 0 && (
          <div className="hidden sm:block">
            <IconTooltipButton
              tooltip="Clear chat"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              onClick={onClearChat}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-stone-200 bg-white text-stone-500 shadow-sm transition-colors hover:border-stone-300 hover:text-stone-900 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-300 dark:hover:text-stone-100"
              aria-label="Clear chat"
            >
              <XCircle size={16} weight="duotone" />
            </IconTooltipButton>
          </div>
        )}
      </div>
    </motion.header>
  )
}
