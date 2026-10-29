import { useMemo } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Card, DataTable, Loaded, Page, Section, StatTile, td, th } from '../components/ui'
import { useDiyMatrix, useMeta, useSeasonFile } from '../data/api'
import type { DiyMatrix, Meta, SeasonFile } from '../data/contract'
import { capMarket, decodeWeights, encodeWeights, isSetId, lastSeason, MARKET_GROUP_CAP, seasonGames, summarize, weekTable, weightsFor, type SetId } from '../diy'
import { llVsMarket, pct } from '../lib/format'
import { WeekChart } from './season/WeekChart'
import { GamesTable } from './season/GamesTable'

const SET_NAMES: Record<SetId, string> = {
  yours: 'Your weights (from Build your own)',
  traditionalist: 'The Traditionalist',
  analyst: 'The Analyst',
  sharp: 'The Sharp',
  student: 'The Student',
}

export default function SeasonPage() {
  const { year } = useParams()
  const meta = useMeta()
  const matrix = useDiyMatrix()
  return (
    <Page
      title={`Season view${year ? `: ${year}` : ''}`}
      lede="Every game of a season, scored with a set of weights. Open it from Build your own to see why a season went well or badly. Games are listed by week; click a column header to sort."
    >
      <Loaded q={meta} what="the groups">
        {(m) => <Loaded q={matrix} what="the game matrix">{(mx) => <SeasonGate meta={m} matrix={mx} year={year} />}</Loaded>}
      </Loaded>
    </Page>
  )
}

function SeasonGate({ meta, matrix, year }: { meta: Meta; matrix: DiyMatrix; year?: string }) {
  const first = matrix.first_scored
  const last = lastSeason(matrix)
  const n = Number(year)
  if (!year || !Number.isInteger(n) || n < first || n > last) {
    return (
      <Card>
        <p className="font-medium">No games for {year ?? 'that season'}.</p>
        <p className="mt-1 text-ink-2">Season views cover {first} to {last}. <Link className="text-accent underline" to={`/season/${last}`}>Open {last}</Link>.</p>
      </Card>
    )
  }
  return <SeasonBody meta={meta} matrix={matrix} season={n} first={first} last={last} />
}

function SeasonBody({ meta, matrix, season, first, last }: { meta: Meta; matrix: DiyMatrix; season: number; first: number; last: number }) {
  const [sp, setSp] = useSearchParams()
  const navigate = useNavigate()
  const q = useSeasonFile(season)
  const wParam = sp.get('w') ?? ''
  const yours = useMemo(() => decodeWeights(wParam), [wParam])
  const hasYours = Object.keys(yours).length > 0
  const setParam = sp.get('set')
  const setId: SetId = isSetId(setParam) && (setParam !== 'yours' || hasYours) ? setParam : hasYours ? 'yours' : 'student'
  const team = sp.get('team') ?? ''
  const put = (k: string, v: string) => setSp((prev) => { const n = new URLSearchParams(prev); if (v) n.set(k, v); else n.delete(k); return n }, { replace: true })
  const setIds = (Object.keys(SET_NAMES) as SetId[]).filter((s) => s !== 'yours' || hasYours)
  const years = Array.from({ length: last - first + 1 }, (_, i) => first + i)
  const names = (id: SetId) => (id === 'yours' ? SET_NAMES.yours : meta.approaches.find((a) => a.id === id)?.name ?? SET_NAMES[id])

  return (
    <>
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col text-[13px] text-ink-3">
          Season
          <select className="mt-1 rounded-md border border-line bg-surface-1 px-2 py-1.5 text-[15px] text-ink" value={season} onChange={(e) => navigate({ pathname: `/season/${e.target.value}`, search: sp.toString() })}>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label className="flex flex-col text-[13px] text-ink-3">
          Weights
          <select className="mt-1 rounded-md border border-line bg-surface-1 px-2 py-1.5 text-[15px] text-ink" value={setId} onChange={(e) => put('set', e.target.value)}>
            {setIds.map((s) => <option key={s} value={s}>{names(s)}</option>)}
          </select>
        </label>
        {hasYours && (
          <Link className="pb-2 text-accent underline" to={`/build?w=${encodeWeights(yours)}`}>Back to Build your own</Link>
        )}
      </div>
      <Loaded q={q} what={`the ${season} games`}>
        {(doc) => <SeasonResults doc={doc} meta={meta} matrix={matrix} setId={setId} yours={yours} team={team} onTeam={(t) => put('team', t)} />}
      </Loaded>
    </>
  )
}

function SeasonResults({ doc, meta, matrix, setId, yours, team: asked, onTeam }: {
  doc: SeasonFile; meta: Meta; matrix: DiyMatrix; setId: SetId; yours: Record<string, number>; team: string; onTeam: (t: string) => void
}) {
  const weights = useMemo(() => weightsFor(setId, matrix, yours), [setId, matrix, yours])
  const all = useMemo(() => seasonGames(doc, matrix, weights), [doc, matrix, weights])
  const teams = useMemo(() => [...new Set([...doc.home, ...doc.away])].sort(), [doc])
  // a ?team= carried over from another season may not exist in this one (e.g. LV before 2020)
  const team = teams.includes(asked) ? asked : ''
  const games = team ? all.filter((g) => g.home === team || g.away === team) : all
  const sum = summarize(games)
  const wk = weekTable(games)
  const best = wk.length ? wk.reduce((a, b) => (b.edge > a.edge ? b : a)) : null
  const worst = wk.length ? wk.reduce((a, b) => (b.edge < a.edge ? b : a)) : null
  const capped = setId === 'yours' && capMarket(yours)[1]
  const scope = team ? `${team}, ${doc.season}` : `all ${games.length} games of ${doc.season}`
  const signedEdge = (x: number) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(3)}`

  return (
    <>
      <Section
        title={`${setId === 'yours' ? 'Your weights' : meta.approaches.find((a) => a.id === setId)?.name ?? setId}, ${doc.season}`}
        aside={
          <label className="text-[13px] text-ink-3">
            Team{' '}
            <select className="rounded-md border border-line bg-surface-1 px-2 py-1 text-[14px] text-ink" value={team} onChange={(e) => onTeam(e.target.value)}>
              <option value="">All teams</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
        }
      >
        {capped && <p className="mb-2 text-[13px] text-ink-2">Market behavior is capped at {Math.round(MARKET_GROUP_CAP * 100)}% of the budget, so its weight was reduced.</p>}
        {setId === 'yours' && !Object.values(yours).some(Boolean) ? (
          <p className="text-[var(--warning)]">Those weights are all zero.</p>
        ) : !sum ? (
          <p className="text-ink-2">No games for this team in {doc.season}.</p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <StatTile
                label="How far off your probabilities were"
                help="Log loss: a penalty for being wrong that grows fast when you were confident. Lower is better; always saying 50% scores 0.693."
                value={sum.log_loss.toFixed(3)}
                sub={sum.market_log_loss == null ? 'no market line' : llVsMarket(sum.log_loss, sum.market_log_loss)}
              />
              <StatTile
                label="Picks right"
                help="A pick is the team you gave more than a 50% chance. The market's favorite is the comparison."
                value={`${sum.right} of ${sum.n} (${pct(sum.right / sum.n)})`}
                sub={`market ${sum.market_right} of ${sum.market_n} (${pct(sum.market_n ? sum.market_right / sum.market_n : null)})`}
              />
              <StatTile
                label="Best week"
                help="Average improvement over the market's log loss per game that week."
                value={best ? `Week ${best.week}` : '–'}
                sub={best ? `${signedEdge(best.edge)} per game over ${best.games} games` : undefined}
              />
            </div>
            {worst && best && (
              <p className="mt-2 text-[13px] text-ink-3">
                Worst week: Week {worst.week} ({signedEdge(worst.edge)} per game over {worst.games} games). Scope: {scope}. Edge = the market's log loss minus yours, so positive means you were closer to what happened.
              </p>
            )}
            {wk.length > 0 && (
              <div className="mt-3">
                <WeekChart rows={wk} />
                <DataTable>
                  <table className="w-full border-collapse text-[13px]">
                    <thead><tr><th className={th}>Week</th><th className={th}>Games</th><th className={th}>Edge per game</th><th className={th}>Picks right</th></tr></thead>
                    <tbody>{wk.map((w) => <tr key={w.week}><td className={td}>{w.week}</td><td className={td}>{w.games}</td><td className={`${td} tabular`}>{signedEdge(w.edge)}</td><td className={td}>{w.right}</td></tr>)}</tbody>
                  </table>
                </DataTable>
              </div>
            )}
          </>
        )}
      </Section>
      {sum && <Section title="Every game"><GamesTable games={games} meta={meta} /></Section>}
    </>
  )
}
