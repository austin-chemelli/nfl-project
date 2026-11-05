/** The one-answer-first row of tiles at the top of a page or tab (ADR 0017). */
import { Children, type ReactNode } from 'react'
import { colorVar } from '../lib/models'
import { Swatch } from './ui'
import { useSetTab } from './Tabs'

/** `tab` makes the tile a button that sets `?tab=` (no page navigation); without it the tile is static. `accent` colors its top edge, by default the approach's. */
export function Tile({ label, value, sub, tab, modelId, accent }: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tab?: string
  modelId?: string
  accent?: string
}) {
  const setTab = useSetTab()
  // switch the tab, then move focus to it so the change is seen (it can be below the fold on a phone) and announced
  const open = (id: string) => {
    setTab(id)
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[role="tab"][data-tab-id="${CSS.escape(id)}"]`)?.focus())
  }
  const body = (
    <>
      <span className="flex items-center gap-1.5 text-[13px] text-ink-3">
        {modelId && <Swatch modelId={modelId} />}
        <span>{label}</span>
      </span>
      <span className="tabular mt-1 block text-xl font-semibold leading-tight">{value}</span>
      {sub && <span className="mt-1 block text-[13px] text-ink-2">{sub}</span>}
    </>
  )
  const base = 'block min-w-0 rounded-lg border border-t-2 border-line bg-surface-1 p-3 text-left'
  const edge = accent ?? (modelId ? colorVar(modelId) : undefined)
  const style = edge ? { borderTopColor: edge } : undefined
  if (tab)
    return (
      <button type="button" onClick={() => open(tab)} style={style} className={`${base} hover:bg-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]`}>
        {body}
      </button>
    )
  return <div className={base} style={style}>{body}</div>
}

export function SummaryStrip({ children, label = 'Summary' }: { children: ReactNode; label?: string }) {
  return (
    <div role="group" aria-label={label} className={`grid grid-cols-2 gap-2 sm:grid-cols-3 ${Children.count(children) === 4 ? 'lg:grid-cols-4' : 'lg:grid-cols-5'}`}>
      {children}
    </div>
  )
}
