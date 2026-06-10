import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { PaperPlaneTilt, Sparkle } from './Icons'
import IconTooltipButton from './IconTooltipButton'

export default function ChatInput({ value, onChange, onSubmit, loading, focusToken, queued }) {
  const textareaRef = useRef(null)
  const [focused, setFocused] = useState(false)

  useEffect(() => {
    const node = textareaRef.current
    if (!node) return
    node.style.height = '0px'
    node.style.height = `${Math.min(node.scrollHeight, 148)}px`
  }, [value])

  useEffect(() => {
    if (focusToken == null) return
    textareaRef.current?.focus()
  }, [focusToken])

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <motion.form initial={false} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      onSubmit={onSubmit}
      className="shrink-0 border-t border-stone-200/70 bg-white/78 px-3 py-3 backdrop-blur-xl dark:border-stone-800 dark:bg-stone-950 sm:px-6 sm:py-4">
      <motion.div
        className="mx-auto max-w-3xl"
        animate={{ y: focused ? -2 : 0 }}
        transition={{ type: 'spring', stiffness: 420, damping: 32 }}
      >
        {queued && (
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-stone-600 dark:text-stone-200">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-stone-500" />
            Message queued — will send when current response completes
          </div>
        )}
        <div className={`relative flex min-h-[56px] items-end gap-2 rounded-2xl border bg-white px-3 py-2 shadow-lg transition-colors dark:bg-stone-950 ${
          focused
            ? 'border-stone-300 shadow-stone-950/[0.08] ring-4 ring-stone-500/10 dark:border-stone-800 dark:shadow-stone-950/20'
            : 'border-stone-200 shadow-stone-950/[0.06] dark:border-stone-800 dark:shadow-black/20'
        }`}>
          <Sparkle size={17} weight="duotone" className="mb-2.5 shrink-0 text-stone-500 dark:text-stone-200" />
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={onChange}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder={queued ? "Message queued — will send when current response completes..." : "Ask about containers, yards, or videos..."}
            className="max-h-[148px] min-h-[36px] flex-1 resize-none bg-transparent py-2 text-[15px] leading-6 text-stone-800 outline-none placeholder:text-stone-400 disabled:opacity-50 dark:text-stone-100 dark:placeholder:text-stone-500"
          />
          <IconTooltipButton
            tooltip="Send message"
            type="submit"
            disabled={!value.trim()}
            whileHover={{ scale: value.trim() ? 1.05 : 1 }}
            whileTap={{ scale: value.trim() ? 0.94 : 1 }}
            className="mb-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-stone-900 text-stone-50 shadow-lg shadow-stone-950/20 transition-colors hover:bg-stone-800 disabled:bg-stone-200 disabled:text-stone-400 disabled:shadow-none dark:bg-stone-100 dark:text-stone-950 dark:hover:bg-white dark:disabled:bg-stone-800 dark:disabled:text-stone-600"
            aria-label="Send message"
          >
            <PaperPlaneTilt size={18} weight="duotone" />
          </IconTooltipButton>
        </div>
      </motion.div>
    </motion.form>
  )
}
