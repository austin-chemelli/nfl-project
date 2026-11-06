/** URL-synced tabs (`?tab=<id>`), WAI-ARIA tabs pattern: roving tabindex, Left/Right/Home/End. Only the active panel renders. */
import { useCallback, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { useSearchParams } from 'react-router'

export type TabDef = { id: string; label: ReactNode; content: ReactNode }

/** Setter for `?tab=` that replaces history (shared by Tabs and Tile links). */
// oxlint-disable-next-line react/only-export-components
export function useSetTab() {
  const [, setParams] = useSearchParams()
  return useCallback(
    (id: string) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('tab', id)
          return next
        },
        { replace: true, preventScrollReset: true },
      )
    },
    [setParams],
  )
}

/** The active tab id from `?tab=` (falling back to `defaultId` when missing or unknown) and its setter. */
// oxlint-disable-next-line react/only-export-components
export function useTabParam(defaultId: string, validIds: readonly string[]) {
  const [params] = useSearchParams()
  const setTab = useSetTab()
  const raw = params.get('tab')
  const active = raw != null && validIds.includes(raw) ? raw : defaultId
  return [active, setTab] as const
}

export function Tabs({ tabs, default: defaultId, label }: { tabs: TabDef[]; default?: string; label?: string }) {
  const base = useId()
  const ids = tabs.map((t) => t.id)
  const [active, setTab] = useTabParam(defaultId && ids.includes(defaultId) ? defaultId : (ids[0] ?? ''), ids)
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})
  const current = tabs.find((t) => t.id === active)

  function onKey(e: KeyboardEvent) {
    const i = ids.indexOf(active)
    let n = -1
    if (e.key === 'ArrowRight') n = (i + 1) % ids.length
    else if (e.key === 'ArrowLeft') n = (i - 1 + ids.length) % ids.length
    else if (e.key === 'Home') n = 0
    else if (e.key === 'End') n = ids.length - 1
    if (n < 0) return
    e.preventDefault()
    setTab(ids[n])
    refs.current[ids[n]]?.focus()
  }

  return (
    <div>
      <div className="overflow-x-auto border-b border-line">
        <div role="tablist" aria-label={label} onKeyDown={onKey} className="flex min-w-max gap-1">
          {tabs.map((t) => {
            const on = t.id === active
            return (
              <button
                key={t.id}
                ref={(el) => {
                  refs.current[t.id] = el
                }}
                type="button"
                role="tab"
                data-tab-id={t.id}
                id={`${base}-tab-${t.id}`}
                aria-selected={on}
                aria-controls={`${base}-panel-${t.id}`}
                tabIndex={on ? 0 : -1}
                onClick={() => setTab(t.id)}
                className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[14px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] ${on ? 'border-[var(--accent)] font-medium text-ink' : 'border-transparent text-ink-2 hover:text-ink'}`}
              >
                {t.label}
              </button>
            )
          })}
        </div>
      </div>
      {current && (
        <div key={current.id} role="tabpanel" id={`${base}-panel-${current.id}`} aria-labelledby={`${base}-tab-${current.id}`} tabIndex={0} className="tab-panel-in scroll-mt-32 pt-5 focus-visible:outline-none">
          {current.content}
        </div>
      )}
    </div>
  )
}
