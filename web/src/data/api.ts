/**
 * Data access: one fetch per JSON file, validated with the zod contract, cached by TanStack Query.
 * Production reads the public bucket (VITE_DATA_URL); `npm run dev` reads the local data/ folder
 * through the Vite plugin at /data.
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import type { z } from 'zod'
import * as C from './contract'

export const DATA_URL: string = (
  import.meta.env.VITE_DATA_URL ??
  (import.meta.env.DEV ? '/data' : 'https://storage.googleapis.com/nfl-project-prod-site')
).replace(/\/$/, '')

export class DataError extends Error {
  readonly path: string
  readonly notFound: boolean
  constructor(path: string, message: string, notFound = false) {
    super(`${path}: ${message}`)
    this.path = path
    this.notFound = notFound
  }
}

/** A file that doesn't exist (yet): a week without a slate, a game without a detail file. */
export const isNotFound = (e: unknown): boolean => e instanceof DataError && e.notFound

export async function fetchJson<S extends z.ZodType>(path: string, schema: S): Promise<z.infer<S>> {
  const res = await fetch(`${DATA_URL}/${path}`)
  // GCS answers 403 for a missing object when listing isn't public
  if (res.status === 404 || res.status === 403) throw new DataError(path, 'not found', true)
  if (!res.ok) throw new DataError(path, `HTTP ${res.status}`)
  const parsed = schema.safeParse(await res.json())
  if (!parsed.success) {
    // A contract drift between site.py and this app: fail loudly, with the first issues.
    throw new DataError(path, `unexpected shape: ${parsed.error.issues.slice(0, 3).map((i) => `${i.path.join('.')} ${i.message}`).join('; ')}`)
  }
  return parsed.data
}

const pad = (n: number) => String(n).padStart(2, '0')
const FIVE_MIN = 5 * 60 * 1000

function useJson<S extends z.ZodType>(key: string, path: string | null, schema: S): UseQueryResult<z.infer<S>> {
  return useQuery({
    queryKey: [key, path],
    queryFn: () => fetchJson(path as string, schema),
    enabled: path !== null,
    staleTime: FIVE_MIN,
    retry: (n, e) => !isNotFound(e) && n < 1,
  })
}

export const useMeta = () => useJson('meta', 'site/meta.json', C.Meta)
export const useSlate = (season?: number, week?: number) =>
  useJson('slate', season && week ? `site/slate_${season}_${pad(week)}.json` : null, C.Slate)
export const useGame = (id?: string) => useJson('game', id ? `site/game/${id}.json` : null, C.Game)
export const useTracker = () => useJson('tracker', 'site/tracker.json', C.Tracker)
export const useHypotheses = () => useJson('hypotheses', 'site/hypotheses.json', C.Hypotheses)
export const useCoaches = () => useJson('coaches', 'site/coaches.json', C.Coaches)
export const useDiyMatrix = () => useJson('diy', 'site/diy_matrix.json', C.DiyMatrix)
export const useSeasonFile = (season?: number) =>
  useJson('season', season ? `site/season_${season}.json` : null, C.SeasonFile)
export const useAudit = () => useJson('audit', 'site/audit.json', C.Audit)
