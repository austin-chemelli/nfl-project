/**
 * Resolves the saved approach against the published data once for the whole app (ADR 0034):
 * maps it onto the current registry, checks its calibration against the data's key, refits it in
 * the background when the models changed (loading the Build matrix only then), and decides which
 * line the pages lead with.
 */
import { useEffect, useMemo, type ReactNode } from 'react'
import { useDiyMatrix, useMeta } from '../data/api'
import { normalize } from '../diy'
import { APPROACHES, HEADLINE, setYouName } from '../lib/models'
import { LinesContext, NO_LINES, YOU, type Lines } from './current'
import { calibrate, capLive, customLine, LIVE_ONLY, youWeights } from './line'
import { migrate, updateSaved, useSaved } from './store'

export function YouProvider({ children }: { children: ReactNode }) {
  const saved = useSaved()
  const meta = useMeta()
  const custom = meta.data?.custom ?? null
  const migration = useMemo(
    () => (saved && custom ? migrate(saved, custom.groups, custom.registry_version) : null),
    [saved, custom],
  )
  const live = custom?.live_only ?? LIVE_ONLY
  // a line needs weight on a group with history: the calibration is fitted on those
  const scorable = migration != null && normalize(capLive(migration.points, live)[0]).total > 0
  const stale = saved != null && custom != null && scorable && saved.calib?.key !== custom.key
  const matrix = useDiyMatrix(stale)

  useEffect(() => {
    // refit after a model update: the matrix must be the one the data names
    if (!stale || !matrix.data || !custom || !migration) return
    if ((matrix.data as { key?: string }).key !== custom.key) return
    const { a, c } = calibrate(youWeights(migration.points, live), matrix.data, custom.trained_through + 1)
    updateSaved({ calib: { key: custom.key, a, c } })
  }, [stale, matrix.data, custom, migration, live])

  const value: Lines = useMemo(() => {
    setYouName(saved?.name ?? 'You')
    if (!saved) return NO_LINES
    const base = { saved, approaches: NO_LINES.approaches, headline: HEADLINE }
    if (!custom || !migration || !scorable) return { ...base, you: null, status: 'unavailable' }
    // a failed matrix fetch must not leave the reader waiting on "updating" for good
    if (saved.calib?.key !== custom.key) return { ...base, you: null, status: matrix.isError ? 'unavailable' : 'calibrating' }
    return {
      saved,
      status: 'ready',
      headline: saved.is_default ? YOU : HEADLINE,
      approaches: APPROACHES,
      you: {
        name: saved.name,
        points: migration.points,
        line: customLine(migration.points, saved.calib, live),
        isDefault: saved.is_default,
        savedAt: saved.saved_at,
        migration,
      },
    }
  }, [saved, custom, migration, scorable, live, matrix.isError])

  return <LinesContext.Provider value={value}>{children}</LinesContext.Provider>
}
