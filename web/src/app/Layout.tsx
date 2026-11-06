import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, ScrollRestoration, useLocation } from 'react-router'
import { useMeta } from '../data/api'
import { ago, kickoffEt } from '../lib/format'
import { useTheme, type Theme } from './theme'
import { isHidden } from '../lib/hiddenPages'

const NAV = [
  { to: '/', label: 'This week', end: true },
  { to: '/league', label: 'League' },
  { to: '/tracker', label: 'Tracker' },
  { to: '/hypotheses', label: 'Evidence' },
  { to: '/coaches', label: 'Coaches' },
  { to: '/build', label: 'Build' },
  { to: '/method', label: 'How it works' },
]

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <Outlet />
      </main>
      <Footer />
      <ScrollRestoration />
    </div>
  )
}

/** A mask-image fade on each edge of the nav that has more to scroll; the active link is kept in view. */
function useNavFade() {
  const ref = useRef<HTMLElement>(null)
  const [edges, setEdges] = useState({ left: false, right: false })
  const { pathname } = useLocation()
  const measure = useCallback(() => {
    const el = ref.current
    if (!el) return
    const left = el.scrollLeft > 1
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
    setEdges((e) => (e.left === left && e.right === right ? e : { left, right }))
  }, [])
  useEffect(() => {
    const el = ref.current
    if (!el) return
    measure()
    el.addEventListener('scroll', measure, { passive: true })
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    ro?.observe(el)
    return () => {
      el.removeEventListener('scroll', measure)
      ro?.disconnect()
    }
  }, [measure])
  useEffect(() => {
    ref.current?.querySelector('[aria-current="page"]')?.scrollIntoView?.({ inline: 'nearest', block: 'nearest' })
  }, [pathname])
  const stops = [edges.left ? 'transparent, #000 24px' : '#000, #000', edges.right ? '#000 calc(100% - 24px), transparent' : '#000, #000'].join(', ')
  const style = edges.left || edges.right ? { maskImage: `linear-gradient(to right, ${stops})`, WebkitMaskImage: `linear-gradient(to right, ${stops})` } : undefined
  return { ref, style }
}

function Header() {
  const [theme, setTheme] = useTheme()
  const { ref: navRef, style: navStyle } = useNavFade()
  const next: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
  return (
    <header className="sticky top-0 z-20 bg-surface-1/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-x-6 gap-y-1 px-4 py-2 sm:px-6">
        <NavLink to="/" className="shrink-0 font-semibold text-ink hover:no-underline">NFL approaches</NavLink>
        <nav ref={navRef} style={navStyle} aria-label="Main" className="-mx-1 flex min-w-0 flex-1 scroll-px-7 gap-1 overflow-x-auto text-[14px]">
          {NAV.filter((n) => !isHidden(n.to)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `shrink-0 rounded px-2 py-1 hover:no-underline ${isActive ? 'bg-accent/20 font-medium text-ink' : 'text-ink-2 hover:text-ink'}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => setTheme(next[theme])}
          className="shrink-0 rounded border border-line px-2 py-0.5 text-[12px] text-ink-2 hover:text-ink"
          aria-label={`Theme: ${theme}. Switch to ${next[theme]}.`}
          title={`Theme: ${theme}`}
        >
          {theme === 'system' ? 'Auto' : theme === 'light' ? 'Light' : 'Dark'}
        </button>
      </div>
      <div className="brand-rule" />
    </header>
  )
}

function Footer() {
  const meta = useMeta()
  return (
    <footer className="mt-12 border-t border-line text-[13px] text-ink-3">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 sm:px-6">
        {meta.data && (
          <div>
            Data updated {ago(meta.data.generated_at)}
            {meta.data.last_lock
              ? ` · last lock ${kickoffEt(meta.data.last_lock.lock_ts)} (week ${meta.data.last_lock.week}${meta.data.last_lock.slot ? `, ${meta.data.last_lock.slot}` : ''})`
              : ' · no public locks yet this season'}
          </div>
        )}
        <div>
          Fan-made and not affiliated with the NFL or any team. Data from{' '}
          <a href="https://github.com/nflverse">nflverse</a> (play-by-play, schedules, injuries) and FTN charting via
          nflverse; odds from The Odds API. Derived data CC BY-SA 4.0; code MIT on{' '}
          <a href="https://github.com/austin-chemelli/nfl-project">GitHub</a>. Not betting advice.
        </div>
      </div>
    </footer>
  )
}
