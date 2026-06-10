import { createPortal } from 'react-dom'
import { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react'
import { motion } from 'framer-motion'

export default function IconTooltipButton({
  children,
  tooltip,
  className = '',
  ...props
}) {
  const buttonRef = useRef(null)
  const tooltipRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState(null)

  const updatePosition = useCallback(() => {
    const node = buttonRef.current
    const tip = tooltipRef.current
    if (!node || !tip || typeof window === 'undefined') return
    const rect = node.getBoundingClientRect()
    const gap = 4
    const padding = 8
    const tipWidth = tip.offsetWidth || 0
    const tipHeight = tip.offsetHeight || 0
    const left = Math.min(
      Math.max(rect.left + (rect.width / 2) - (tipWidth / 2), padding),
      Math.max(padding, window.innerWidth - padding - tipWidth),
    )
    const top = Math.min(
      rect.bottom + gap,
      Math.max(padding, window.innerHeight - padding - tipHeight),
    )
    setPosition({
      top,
      left,
    })
  }, [])

  useLayoutEffect(() => {
    if (!open || !tooltip) return
    updatePosition()
  }, [open, tooltip, updatePosition])

  useEffect(() => {
    if (!open) return undefined
    const handle = () => updatePosition()
    window.addEventListener('resize', handle)
    window.addEventListener('scroll', handle, true)
    return () => {
      window.removeEventListener('resize', handle)
      window.removeEventListener('scroll', handle, true)
    }
  }, [open, updatePosition])

  return (
    <>
      <motion.button
        ref={buttonRef}
        {...props}
        className={className}
        onMouseEnter={(event) => {
          props.onMouseEnter?.(event)
          setOpen(true)
        }}
        onMouseLeave={(event) => {
          props.onMouseLeave?.(event)
          setOpen(false)
          setPosition(null)
        }}
        onFocus={(event) => {
          props.onFocus?.(event)
          setOpen(true)
        }}
        onBlur={(event) => {
          props.onBlur?.(event)
          setOpen(false)
          setPosition(null)
        }}
      >
        {children}
      </motion.button>
      {open && tooltip && typeof document !== 'undefined' && createPortal(
        <span
          ref={tooltipRef}
          className="pointer-events-none fixed z-[9999] whitespace-nowrap rounded-lg border border-stone-200 bg-white px-2.5 py-1 text-[11px] font-medium text-stone-600 shadow-lg shadow-stone-950/10 dark:border-stone-800 dark:bg-stone-950 dark:text-stone-200"
          style={{
            top: position?.top ?? 0,
            left: position?.left ?? 0,
            visibility: position ? 'visible' : 'hidden',
          }}
        >
          {tooltip}
        </span>,
        document.body,
      )}
    </>
  )
}
