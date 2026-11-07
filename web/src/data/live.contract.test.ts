/**
 * The deployed data against this code's contract (ADR 0023). Skipped unless LIVE_CONTRACT=1: CI runs
 * it after the data rebuild and before the web deploy, so a web change that needs data the jobs
 * don't write yet (or a job change that drops a field the page still needs) stops the deploy instead
 * of breaking the live site. Reads the public bucket, or LIVE_DATA_URL.
 */
import { describe, expect, it } from 'vitest'
import type { z } from 'zod'
import * as C from './contract'

const BASE = process.env.LIVE_DATA_URL ?? 'https://storage.googleapis.com/nfl-project-prod-site'
const pad = (n: number) => String(n).padStart(2, '0')

type Result = { path: string; problem: string }

async function get(path: string): Promise<unknown | null> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(`${BASE}/${path}?v=${Date.now()}`)
      if (res.status === 404 || res.status === 403) return null // not built (yet): nothing to break
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return await res.json()
    } catch (e) {
      if (attempt === 2) throw new Error(`${path}: ${String(e)}`)
    }
  }
  return null
}

async function check(path: string, schema: z.ZodType, out: Result[]): Promise<unknown | null> {
  const body = await get(path)
  if (body == null) return null
  const parsed = schema.safeParse(body)
  if (!parsed.success) {
    const issues = parsed.error.issues.slice(0, 3).map((i) => `${i.path.join('.')}: ${i.message}`).join('; ')
    out.push({ path, problem: issues })
    return null
  }
  return parsed.data
}

describe.skipIf(!process.env.LIVE_CONTRACT)('live data parses with this contract', () => {
  it('every kind of site file the pages read', { timeout: 120_000 }, async () => {
    const bad: Result[] = []
    const meta = (await check('site/meta.json', C.Meta, bad)) as C.Meta | null
    expect(meta, 'site/meta.json must exist and parse').not.toBeNull()
    const { season, current_week: week } = meta!
    for (const [path, schema] of [
      ['site/tracker.json', C.Tracker], ['site/hypotheses.json', C.Hypotheses], ['site/coaches.json', C.Coaches],
      ['site/diy_matrix.json', C.DiyMatrix], ['site/league.json', C.LeagueFile], ['site/similar.json', C.SimilarFile],
      ['site/audit.json', C.Audit], [`site/season_${season - 1}.json`, C.SeasonFile],
    ] as const) await check(path, schema, bad)

    const teams = (await check('site/teams.json', C.TeamsFile, bad)) as C.TeamsFile | null
    for (const code of Object.keys(teams?.teams ?? {})) await check(`site/team/${code}.json`, C.TeamFile, bad)

    // this week and last week, and a finished and an upcoming game from them
    const ids: string[] = []
    for (const w of [week, week - 1].filter((w) => w >= 1)) {
      const slate = (await check(`site/slate_${season}_${pad(w)}.json`, C.Slate, bad)) as C.Slate | null
      ids.push(...(slate?.games.slice(0, 2).map((g) => g.game_id) ?? []))
      await check(`site/recap_${season}_${pad(w)}.json`, C.WeekRecap, bad)
    }
    for (const id of ids) {
      await check(`site/game/${id}.json`, C.Game, bad)
      await check(`site/retro/${id}.json`, C.RetroGame, bad)
    }

    expect(bad, bad.map((b) => `${b.path}: ${b.problem}`).join('\n')).toEqual([])
  })
})
