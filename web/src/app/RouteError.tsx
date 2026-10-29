import { useEffect } from 'react'
import { Link, useRouteError } from 'react-router'
import { Page } from '../components/ui'

const RELOADED = 'nfl-chunk-reload'

/** A lazy page from an older deploy whose hashed file is gone: one reload fetches the new build. */
function isStaleChunk(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : String(error)
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported/i.test(msg)
}

export function RouteError() {
  const error = useRouteError()
  const stale = isStaleChunk(error)
  useEffect(() => {
    if (!stale) return
    try {
      if (sessionStorage.getItem(RELOADED)) return
      sessionStorage.setItem(RELOADED, '1')
    } catch {
      return // storage blocked: don't risk a reload loop
    }
    window.location.reload()
  }, [stale])
  return (
    <Page title="Something went wrong">
      <p className="text-ink-2">
        {stale ? 'The site was updated while this tab was open.' : 'This page hit an error while rendering.'}{' '}
        <button type="button" className="text-accent underline" onClick={() => window.location.reload()}>
          Reload
        </button>{' '}
        or go <Link to="/">back to this week's games</Link>.
      </p>
      {!stale && <p className="mt-2 text-[13px] text-ink-3">{error instanceof Error ? error.message : String(error)}</p>}
    </Page>
  )
}
