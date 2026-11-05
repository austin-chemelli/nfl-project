/**
 * The hover layer for the SVG charts: one HTML card following the pointer, on keyboard focus and on a
 * tap too. It adds detail and never carries the only copy of a value: each chart still prints its
 * numbers. Value first, label after, a short stroke keying the series.
 */
import { useRef, useState, type FocusEvent, type PointerEvent, type ReactNode } from 'react'

type At = { key: string; x: number; y: number; width: number; above: boolean }

const WIDTH = 256

/** `bind(key)` goes on a row's `<g>`; `at` is the row under the pointer; `card(content)` draws it. */
// oxlint-disable-next-line react/only-export-components
export function useChartTip() {
  const box = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState<At | null>(null)
  const place = (key: string, clientX: number, clientY: number) => {
    const r = box.current?.getBoundingClientRect()
    if (r) setAt({ key, x: clientX - r.left, y: clientY - r.top, width: r.width, above: clientY > window.innerHeight / 2 })
  }
  const bind = (key: string) => ({
    tabIndex: 0,
    onPointerMove: (e: PointerEvent) => place(key, e.clientX, e.clientY),
    onPointerLeave: () => setAt(null),
    onFocus: (e: FocusEvent<SVGGElement>) => {
      const b = e.currentTarget.getBoundingClientRect()
      place(key, b.left + b.width / 2, b.top)
    },
    onBlur: () => setAt(null),
    style: { outline: 'none' },
  })
  const card = (content: ReactNode) => {
    if (!at || !content) return null
    const left = Math.max(0, Math.min(at.x + 14, at.width - WIDTH))
    return (
      <div role="tooltip" data-testid="chart-tip" className="pointer-events-none absolute z-30 rounded-lg border border-line bg-surface-1 p-2.5 text-[13px] leading-snug shadow-xl" style={{ left, top: at.above ? at.y - 12 : at.y + 16, width: WIDTH, transform: at.above ? 'translateY(-100%)' : undefined }}>
        {content}
      </div>
    )
  }
  return { box, at, bind, card }
}

export function TipTitle({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <div className="mb-1.5">
      <div className="font-medium text-ink">{children}</div>
      {note && <div className="mt-0.5 text-[12px] text-ink-3">{note}</div>}
    </div>
  )
}

/** One reading: the key stroke, the value, then what it is. */
export function TipRow({ color, value, label }: { color?: string; value: ReactNode; label: ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span aria-hidden className="inline-block h-[3px] w-3 shrink-0 translate-y-[-3px] rounded-full" style={{ background: color ?? 'var(--text-muted)' }} />
      <span className="tabular font-semibold text-ink">{value}</span>
      <span className="min-w-0 text-ink-2">{label}</span>
    </div>
  )
}

export function TipNote({ children }: { children: ReactNode }) {
  return <div className="mt-1.5 border-t border-line pt-1.5 text-[12px] text-ink-3">{children}</div>
}
