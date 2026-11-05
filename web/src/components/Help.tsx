/**
 * Hover/focus help: a small "?" that shows a description. Every feature, group and metric name on
 * the site should carry one (descriptions come from meta.json, never hard-coded on a page).
 */
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

const TIP_WIDTH = 288 // w-72
const EDGE = 8
const GAP = 4

export function Help({ text, children }: { text: string | null | undefined; children?: ReactNode }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ left: 0, top: 0 })
  const btn = useRef<HTMLButtonElement>(null)
  const tip = useRef<HTMLSpanElement>(null)
  // a tap focuses the button before its click; this lets onFocus skip opening so the click is the one toggle
  const tapping = useRef(false)
  // fixed to the screen and kept on it: an absolute tip ran off a phone's edge and was clipped by scrolling tables
  const place = useCallback(() => {
    const b = btn.current?.getBoundingClientRect()
    if (!b) return
    if (b.bottom < 0 || b.top > window.innerHeight) return setOpen(false)
    const width = Math.min(TIP_WIDTH, 0.8 * window.innerWidth)
    const height = tip.current?.offsetHeight ?? 0
    const below = b.bottom + GAP
    setPos({
      left: Math.max(EDGE, Math.min(b.left, window.innerWidth - width - EDGE)),
      top: below + height > window.innerHeight - EDGE ? Math.max(EDGE, b.top - GAP - height) : below,
    })
  }, [])
  useLayoutEffect(() => {
    if (open) place()
  }, [open, place])
  useEffect(() => {
    if (!open) return
    // iOS Safari doesn't focus a tapped button, so blur may never fire: close on a pointerdown anywhere else
    const away = (e: PointerEvent) => {
      const t = e.target as Node
      if (!btn.current?.contains(t) && !tip.current?.contains(t)) setOpen(false)
    }
    // the tip follows its "?": keyboard focus scrolls the page, and closing here would lose the tip
    document.addEventListener('pointerdown', away)
    window.addEventListener('scroll', place, { capture: true, passive: true })
    return () => {
      document.removeEventListener('pointerdown', away)
      window.removeEventListener('scroll', place, { capture: true })
    }
  }, [open, place])
  if (!text) return <>{children}</>
  return (
    <span className="relative inline-flex items-baseline gap-1">
      {children}
      <button
        type="button"
        aria-describedby={id}
        aria-label="What is this?"
        className="inline-flex h-4 w-4 shrink-0 translate-y-[1px] items-center justify-center rounded-full border border-line text-[10px] leading-none text-ink-3 hover:text-ink focus:outline-2 focus:outline-accent"
        ref={btn}
        onPointerEnter={(e) => e.pointerType === 'mouse' && setOpen(true)}
        onPointerLeave={(e) => e.pointerType === 'mouse' && setOpen(false)}
        onPointerDown={() => {
          tapping.current = true
        }}
        onPointerCancel={() => {
          tapping.current = false
        }}
        onFocus={() => {
          if (tapping.current) tapping.current = false
          else setOpen(true)
        }}
        onBlur={() => setOpen(false)}
        onClick={() => {
          tapping.current = false
          setOpen(!open)
        }}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
      >
        ?
      </button>
      <span
        id={id}
        role="tooltip"
        ref={tip}
        style={pos}
        className={`fixed z-30 w-72 max-w-[80vw] whitespace-normal rounded-md border border-line bg-surface-1 p-2 text-[13px] font-normal normal-case leading-snug tracking-normal text-ink-2 shadow-lg ${open ? 'block' : 'hidden'}`}
      >
        {text}
      </span>
    </span>
  )
}
