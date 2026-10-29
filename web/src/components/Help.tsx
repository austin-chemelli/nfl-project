/**
 * Hover/focus help: a small "?" that shows a description. Every feature, group and metric name on
 * the site should carry one (descriptions come from meta.json, never hard-coded on a page).
 */
import { useId, useRef, useState, type ReactNode } from 'react'

export function Help({ text, children }: { text: string | null | undefined; children?: ReactNode }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [alignRight, setAlignRight] = useState(false)
  const btn = useRef<HTMLButtonElement>(null)
  if (!text) return <>{children}</>
  const show = () => {
    // a "?" near the right edge of a phone opens leftward instead of widening the page
    const r = btn.current?.getBoundingClientRect()
    setAlignRight(!!r && r.left + 296 > window.innerWidth)
    setOpen(true)
  }
  return (
    <span className="relative inline-flex items-baseline gap-1">
      {children}
      <button
        type="button"
        aria-describedby={id}
        aria-label="What is this?"
        className="inline-flex h-4 w-4 shrink-0 translate-y-[1px] items-center justify-center rounded-full border border-line text-[10px] leading-none text-ink-3 hover:text-ink focus:outline-2 focus:outline-accent"
        ref={btn}
        onMouseEnter={show}
        onMouseLeave={() => setOpen(false)}
        onFocus={show}
        onBlur={() => setOpen(false)}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
      >
        ?
      </button>
      <span
        id={id}
        role="tooltip"
        className={`absolute top-full ${alignRight ? 'right-0' : 'left-0'} z-30 mt-1 w-72 max-w-[80vw] rounded-md border border-line bg-surface-1 p-2 text-[13px] font-normal leading-snug text-ink-2 shadow-lg ${open ? 'block' : 'hidden'}`}
      >
        {text}
      </span>
    </span>
  )
}
