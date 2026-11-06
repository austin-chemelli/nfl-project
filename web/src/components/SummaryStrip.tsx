/** The one-answer-first row of tiles at the top of a page or tab (ADR 0017). */
import { Children, type ReactNode } from 'react'
import { colorVar } from '../lib/models'
import { Swatch } from './ui'
import { useSetTab } from './Tabs'

/**
 * Bring a tab's panel into view if it sits below the fold or above the top, then flash it once. Called
 * from a tile click only. The flash lasts 3 x --dur-base, so reduced motion zeroes it, and the scroll is
 * instant under reduced motion. The panel can take a frame to mount after the tab switch, so it retries.
 */
function showPanel(tab: HTMLElement, tries = 3) {
  const panel = document.getElementById(tab.getAttribute('aria-controls') ?? '')
  if (!panel || panel.getAttribute('aria-labelledby') !== tab.id) {
    if (tries > 0) requestAnimationFrame(() => showPanel(tab, tries - 1))
    return
  }
  const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const top = panel.getBoundingClientRect().top
  if (top > window.innerHeight * 0.75 || top < 0) panel.scrollIntoView?.({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  panel.classList.remove('tile-flash')
  void panel.offsetWidth // restart the animation on a second click
  panel.classList.add('tile-flash')
  panel.onanimationend = (e) => { if (e.animationName === 'tile-flash') panel.classList.remove('tile-flash') }
}

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
  const open = (id: string) => {
    setTab(id)
    requestAnimationFrame(() => {
      const tab = document.querySelector<HTMLElement>(`[role="tab"][data-tab-id="${CSS.escape(id)}"]`)
      tab?.focus()
      if (tab) showPanel(tab)
    })
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
