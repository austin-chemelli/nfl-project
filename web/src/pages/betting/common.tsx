/** Small components shared by the betting pages. */
import type { ReactNode } from 'react'

/** One lede sentence under a section's heading. */
export function Lede({ children }: { children: ReactNode }) {
  return <p className="mb-2 text-[14px] text-ink-2">{children}</p>
}

/** A swatch and its meaning, for a chart's line key. */
export function Key({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-ink-2">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden="true">
            <line x1="0" x2="22" y1="3" y2="3" stroke={i.color} strokeWidth="2" strokeDasharray={i.dashed ? '2 3' : undefined} />
          </svg>
          {i.label}
        </span>
      ))}
    </div>
  )
}

/** The problem-gambling line that closes every betting page's fine print. */
export function HelpLine() {
  return (
    <p>
      If betting stops being fun: 1-800-MY-RESET (1-800-697-3738), call, text or chat, from the National Council on Problem Gambling (
      <a href="https://www.ncpgambling.org/" target="_blank" rel="noreferrer noopener">ncpgambling.org</a>).
    </p>
  )
}
