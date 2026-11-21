/**
 * The always-visible mark that pages lead with the reader's own line (ADR 0034), with the one-click
 * way back; also says when a saved line is being refitted or was saved under older groups.
 */
import { Link } from 'react-router'
import { useLines } from './current'
import { setDefault } from './store'

export function YouBar() {
  const { you, status, saved } = useLines()
  if (status === 'calibrating') {
    return <Bar>Updating your line for the new models…</Bar>
  }
  if (!you) {
    if (status !== 'unavailable' || !saved) return null
    return (
      <Bar>
        <span>Your saved approach can't be scored with this week's data, so it isn't shown.</span>
        <Link to="/build">Open it in Build</Link>
      </Bar>
    )
  }
  const m = you.migration
  const moved = m.changed && (m.dropped.length > 0 || m.added.length > 0)
  if (!you.isDefault && !moved) return null
  return (
    <Bar>
      {you.isDefault && (
        <>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: 'var(--series-you)' }} />
            <span>
              Leading with your line, <strong className="font-medium">{you.name}</strong>: unofficial, scored in this browser.
            </span>
          </span>
          <button type="button" onClick={() => setDefault(false)} className="rounded border border-line bg-surface-1 px-2 py-0.5 hover:bg-surface-2">
            Lead with the Student
          </button>
        </>
      )}
      {moved && saved && (
        <span>
          Your approach was saved with older groups
          {m.dropped.length > 0 && `; dropped: ${m.dropped.join(', ')}`}
          {m.added.length > 0 && `; new at 0: ${m.added.join(', ')}`}.
        </span>
      )}
      <Link to="/build">Edit</Link>
    </Bar>
  )
}

function Bar({ children }: { children: React.ReactNode }) {
  return (
    <div role="status" data-you-bar className="border-b border-line bg-surface-2 text-[13px]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1.5 sm:px-6">{children}</div>
    </div>
  )
}

/** "unofficial" beside a number from the reader's own line. */
export function Unofficial({ className = '' }: { className?: string }) {
  return (
    <span className={`ml-1 rounded border border-line px-1 text-[11px] font-normal uppercase tracking-wide text-ink-3 ${className}`} title="Your own line: scored in this browser, never locked, graded or published">
      unofficial
    </span>
  )
}
