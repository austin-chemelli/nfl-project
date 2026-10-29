import { NavLink, Outlet, ScrollRestoration } from 'react-router'
import { useMeta } from '../data/api'
import { ago, kickoffEt } from '../lib/format'
import { useTheme, type Theme } from './theme'

const NAV = [
  { to: '/', label: 'This week', end: true },
  { to: '/tracker', label: 'Tracker' },
  { to: '/hypotheses', label: 'What history says' },
  { to: '/coaches', label: 'Coaches' },
  { to: '/build', label: 'Build your own' },
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

function Header() {
  const [theme, setTheme] = useTheme()
  const next: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface-1/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-x-6 gap-y-1 px-4 py-2 sm:px-6">
        <NavLink to="/" className="shrink-0 font-semibold text-ink hover:no-underline">NFL approaches</NavLink>
        <nav aria-label="Main" className="-mx-1 flex min-w-0 flex-1 gap-1 overflow-x-auto text-[14px]">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `shrink-0 rounded px-2 py-1 hover:no-underline ${isActive ? 'bg-surface-2 font-medium text-ink' : 'text-ink-2 hover:text-ink'}`
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
