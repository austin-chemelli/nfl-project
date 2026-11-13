/**
 * The projected playoff bracket (Austin, 2026-11-12): the Playoff odds tab's default view. One plausible
 * field and path from the simulated odds (`bracket.ts`); every team shows its chance to win that round,
 * its record and its projected final record.
 *
 * With room (about 1,040 px) the conferences face each other: AFC left to right, the Super Bowl in the
 * middle, NFC right to left. Narrower, each conference runs left to right and the Super Bowl sits below.
 * Lines join each team to where it plays next; the NFL reseeds after the wild card, so they are drawn from
 * the boxes' real positions rather than a fixed tree.
 */
import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { LeagueFile, LeagueTeam } from '../../data/contract'
import { TeamLink } from '../../components/TeamLink'
import { teamDotVars } from '../../lib/teamColors'
import { teamInfo } from '../../lib/teams'
import { projectConference, projectSeeds, recordView, superBowl, type ConfBracket, type Game, type OddsMap, type Rec, type Seeded } from './bracket'
import { Move } from './Move'
import { fmtProb, type Conf } from './playoffs'

/** The round a game's winner reaches: each number is the chance to win that game's round. */
type Round = 'div' | 'conf' | 'sb' | 'champ'
const value = (odds: OddsMap, team: string, r: Round | 'playoffs') => (r === 'playoffs' ? odds[team]?.playoffs : odds[team]?.rounds[r]) ?? 0
const ROUND_NAME: Record<Round, string> = { div: 'divisional round', conf: 'conference game', sb: 'Super Bowl', champ: 'title' }
const FACE_OFF_MIN = 1040

export type DecidedGame = { home: string; away: string; winner: 'home' | 'away' }
type Ctx = { odds: OddsMap; was?: OddsMap; standings: Map<string, LeagueTeam>; decided: DecidedGame[] }

const phoneTint = (d: number) => (d >= 0.01 ? 'max-sm:text-[var(--good)]' : d <= -0.01 ? 'max-sm:text-[var(--critical)]' : '')
const recText = (r: Rec) => `${r.w}–${r.l}${r.t ? `–${r.t}` : ''}`
const GOOD = 'var(--good)'
const BAD = 'var(--critical)'

/** "8–3 · proj 12–5": decided wins in green and losses in red; the projection colored when it moved. */
function Records({ team, ctx }: { team: string; ctx: Ctx }) {
  const st = ctx.standings.get(team)
  const o = ctx.odds[team]
  if (!st || !o) return null
  const r = recordView(st, ctx.decided, o.wins.mean, ctx.was?.[team]?.wins.mean)
  const moved = r.projWas ? r.proj.w - r.projWas.w : 0
  const title = `Record ${recText(r.now)}${r.added.w + r.added.l ? ' with your decisions' : ''}; projected to finish ${recText(r.proj)}${r.projWas && moved ? ` (was ${recText(r.projWas)})` : ''}`
  return (
    <span className="tabular block truncate pl-4 text-[11px] text-ink-3" title={title}>
      <span style={r.added.w ? { color: GOOD, fontWeight: 600 } : undefined}>{r.now.w}</span>–<span style={r.added.l ? { color: BAD, fontWeight: 600 } : undefined}>{r.now.l}</span>
      {r.now.t ? `–${r.now.t}` : ''}
      <span> · proj </span>
      <span style={moved ? { color: moved > 0 ? GOOD : BAD, fontWeight: 600 } : undefined}>{recText(r.proj)}</span>
    </span>
  )
}

function TeamLine({ s, round, ctx, state, node }: { s: Seeded; round: Round; ctx: Ctx; state: 'win' | 'lose'; node: string }) {
  const v = value(ctx.odds, s.team, round)
  return (
    <div
      data-matchup
      data-team={s.team}
      data-node={node}
      style={teamDotVars(s.team)}
      title={`${teamInfo(s.team).name}: ${fmtProb(v)} to ${round === 'champ' ? 'win the Super Bowl' : `reach the ${ROUND_NAME[round]}`}`}
      className={`min-w-0 px-1.5 py-1 sm:px-2 ${state === 'lose' ? 'text-ink-3' : 'text-ink'}`}
    >
      <span className="flex min-w-0 items-center gap-1 text-[12px] sm:gap-1.5 sm:text-[13px]">
        <span className="tabular w-3 shrink-0 text-right text-[11px] text-ink-3">{s.seed}</span>
        <span aria-hidden className={`hidden h-2.5 w-2.5 shrink-0 rounded-full sm:inline-block ${state === 'lose' ? 'opacity-50' : ''}`} style={{ background: 'var(--team-home)' }} />
        <TeamLink team={s.team} className={`${state === 'win' ? 'font-semibold' : 'font-medium'} ${state === 'lose' ? 'text-ink-3' : ''}`}>
          {s.team}
        </TeamLink>
        <span className="ml-auto flex shrink-0 items-center">
          {/* on phones the arrow doesn't fit: the number itself turns green or red */}
          <span className={`tabular ${state === 'win' ? 'font-semibold' : ''} ${phoneTint(ctx.was ? v - value(ctx.was, s.team, round) : 0)}`}>{fmtProb(v)}</span>
          {ctx.was && (
            <span className="hidden sm:inline-flex">
              <Move from={value(ctx.was, s.team, round)} to={v} />
            </span>
          )}
        </span>
      </span>
      <Records team={s.team} ctx={ctx} />
    </div>
  )
}

const BOX = 'relative z-[1] overflow-hidden rounded-md bg-surface-1'

function GameBox({ g, round, ctx, col }: { g: Game; round: Round; ctx: Ctx; col: string }) {
  return (
    <div className={`${BOX} divide-y divide-[var(--border)] border border-line`}>
      {[g.a, g.b].map((s) => (
        <div key={s.team} className={s === g.winner ? 'border-l-[3px] border-l-[var(--accent)]' : 'border-l-[3px] border-l-transparent'}>
          <TeamLine s={s} round={round} ctx={ctx} state={s === g.winner ? 'win' : 'lose'} node={`${col}|${s.team}`} />
        </div>
      ))}
    </div>
  )
}

function ByeBox({ s, ctx, col }: { s: Seeded; ctx: Ctx; col: string }) {
  return (
    <div className={`${BOX} border border-dashed border-line`}>
      <div className="border-l-[3px] border-l-[var(--accent)]">
        <TeamLine s={s} round="div" ctx={ctx} state="win" node={`${col}|${s.team}`} />
      </div>
      <div className="px-2 pb-1 text-[11px] text-ink-3">Bye</div>
    </div>
  )
}

function Column({ title, children, right = false }: { title: string; children: ReactNode; right?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col">
      <div className={`mb-1 text-[11px] font-medium uppercase tracking-wide text-ink-3 ${right ? 'text-right' : ''}`}>{title}</div>
      <div className="flex flex-1 flex-col justify-around gap-2">{children}</div>
    </div>
  )
}

/** The three columns of one conference, in reading order or mirrored. */
function confColumns(conf: Conf, b: ConfBracket, ctx: Ctx, mirror: boolean): ReactNode[] {
  const cols = [
    <Column key="wc" title="Wild card" right={mirror}>
      {b.bye.map((s) => <ByeBox key={s.team} s={s} ctx={ctx} col={`${conf}|0`} />)}
      {b.wildCard.map((g) => <GameBox key={g.a.team} g={g} round="div" ctx={ctx} col={`${conf}|0`} />)}
    </Column>,
    <Column key="div" title="Divisional" right={mirror}>
      {b.divisional.map((g) => <GameBox key={g.a.team} g={g} round="conf" ctx={ctx} col={`${conf}|1`} />)}
    </Column>,
    <Column key="conf" title={`${conf} title game`} right={mirror}>
      <GameBox g={b.conference} round="sb" ctx={ctx} col={`${conf}|2`} />
    </Column>,
  ]
  return mirror ? cols.reverse() : cols
}

function ConfTitle({ conf, right = false }: { conf: Conf; right?: boolean }) {
  return (
    <h3 className={`flex items-center gap-2 text-[15px] font-semibold text-ink ${right ? 'justify-end' : ''}`}>
      <span aria-hidden className="inline-block h-3 w-1 rounded-sm" style={{ background: `var(--conf-${conf.toLowerCase()})` }} />
      {conf}
    </h3>
  )
}

function Bubble({ teams, ctx, right = false }: { teams: string[]; ctx: Ctx; right?: boolean }) {
  if (!teams.length) return null
  return <p className={`tabular text-[12px] text-ink-3 ${right ? 'text-right' : ''}`}>Next in line: {teams.map((t) => `${t} ${fmtProb(value(ctx.odds, t, 'playoffs'))}`).join(' · ')}</p>
}

/** Elbow lines from each team's row to its row in the next round, measured from the DOM after layout. */
function useConnectors(box: RefObject<HTMLDivElement | null>, links: [string, string][], dep: string) {
  const [state, setState] = useState<{ paths: string[]; w: number; h: number }>({ paths: [], w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const draw = () => {
      const base = el.getBoundingClientRect()
      const at = (key: string) => el.querySelector<HTMLElement>(`[data-node="${key}"]`)?.getBoundingClientRect()
      const paths: string[] = []
      for (const [from, to] of links) {
        const a = at(from)
        const b = at(to)
        if (!a || !b || !a.width || !b.width) continue
        const ay = a.top + a.height / 2 - base.top
        const by = b.top + b.height / 2 - base.top
        // the rows sit inside a box with a 3px accent; leave a small gap at each end
        let x1: number, x2: number
        if (b.left >= a.right - 1) {
          x1 = a.right - base.left + 1
          x2 = b.left - base.left - 4
        } else if (b.right <= a.left + 1) {
          x1 = a.left - base.left - 4
          x2 = b.right - base.left + 1
        } else continue
        const mx = (x1 + x2) / 2
        paths.push(`M${x1} ${ay}H${mx}V${by}H${x2}`)
      }
      setState({ paths, w: el.clientWidth, h: el.clientHeight })
    }
    draw()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(draw)
    ro.observe(el)
    return () => ro.disconnect()
    // links are captured through `dep`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dep])
  return state
}

function useWidth(ref: RefObject<HTMLDivElement | null>) {
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setW(el.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => setW(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return w
}

const FACE_GRID = 'grid grid-cols-[1fr_1fr_1fr_1.1fr_1fr_1fr_1fr] gap-3'

export function Bracket({ file, odds, was, decided = [], first = 'AFC' }: { file: LeagueFile; odds: OddsMap; was?: OddsMap; decided?: DecidedGame[]; first?: Conf }) {
  const standings = new Map(file.teams.map((t) => [t.team, t]))
  const ctx: Ctx = { odds, was, standings, decided }
  const outer = useRef<HTMLDivElement>(null)
  const faceOff = useWidth(outer) >= FACE_OFF_MIN
  const confs = (['AFC', 'NFC'] as Conf[]).map((conf) => {
    const teams = file.teams.filter((t) => t.conf === conf && odds[t.team]).map((t) => t.team).sort((a, b) => odds[b].playoffs - odds[a].playoffs || a.localeCompare(b))
    const seeds = projectSeeds(teams, odds)
    const b = projectConference(seeds, odds)
    const bubble = teams.filter((t) => !seeds.includes(t)).slice(0, 3)
    return { conf, b, bubble }
  })
  const [afc, nfc] = confs
  const sb = superBowl(afc.b.champ, nfc.b.champ, odds)

  // every team that plays on, from its row to its row in the next round
  const links: [string, string][] = []
  for (const { conf, b } of confs) {
    for (const g of b.divisional) for (const s of [g.a, g.b]) links.push([`${conf}|0|${s.team}`, `${conf}|1|${s.team}`])
    for (const s of [b.conference.a, b.conference.b]) links.push([`${conf}|1|${s.team}`, `${conf}|2|${s.team}`])
    if (faceOff) links.push([`${conf}|2|${b.champ.team}`, `SB|${b.champ.team}`])
  }
  const lines = useRef<HTMLDivElement>(null)
  const dep = `${faceOff}|${links.map((l) => l.join('>')).join(',')}|${Object.values(odds).map((o) => o.playoffs).join(',')}|${decided.length}|${was ? 1 : 0}`
  const { paths, w, h } = useConnectors(lines, links, dep)

  const sbBox = (
    <section aria-label="Projected Super Bowl" className="flex flex-col gap-1">
      <div className="text-center text-[11px] font-medium uppercase tracking-wide text-ink-3">Super Bowl</div>
      <div className={`${BOX} divide-y divide-[var(--border)] border-2 border-[var(--accent)]`}>
        {[sb.afc, sb.nfc].map((s) => (
          <div key={s.team} className={s === sb.winner ? 'border-l-[3px] border-l-[var(--accent)]' : 'border-l-[3px] border-l-transparent'}>
            <TeamLine s={s} round="champ" ctx={ctx} state={s === sb.winner ? 'win' : 'lose'} node={`SB|${s.team}`} />
          </div>
        ))}
      </div>
      <div className="text-center text-[12px] text-ink-2">
        Champion: <span className="font-semibold text-ink">{teamInfo(sb.winner.team).name}</span>
      </div>
    </section>
  )

  return (
    <div ref={outer} className="min-w-0">
      <div ref={lines} className="relative">
        <svg aria-hidden className="pointer-events-none absolute inset-0 z-0" width={w} height={h}>
          {paths.map((d, i) => (
            <path key={i} d={d} fill="none" stroke="var(--text-muted)" strokeOpacity={0.6} strokeWidth={1.5} strokeLinejoin="round" />
          ))}
        </svg>
        {faceOff ? (
          <div className="flex flex-col gap-2">
            <div className={FACE_GRID}>
              <div className="col-span-3"><ConfTitle conf="AFC" /></div>
              <div />
              <div className="col-span-3"><ConfTitle conf="NFC" right /></div>
            </div>
            <div className={FACE_GRID}>
              <section aria-label="AFC projected bracket" className="col-span-3 grid grid-cols-3 gap-3">{confColumns('AFC', afc.b, ctx, false)}</section>
              <div className="flex flex-col justify-center">{sbBox}</div>
              <section aria-label="NFC projected bracket" className="col-span-3 grid grid-cols-3 gap-3">{confColumns('NFC', nfc.b, ctx, true)}</section>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Bubble teams={afc.bubble} ctx={ctx} />
              <Bubble teams={nfc.bubble} ctx={ctx} right />
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {(first === 'NFC' ? [nfc, afc] : [afc, nfc]).map(({ conf, b, bubble }) => (
              <section key={conf} aria-label={`${conf} projected bracket`} className="flex min-w-0 flex-col gap-2">
                <ConfTitle conf={conf} />
                <div className="grid grid-cols-3 gap-2 sm:gap-3">{confColumns(conf, b, ctx, false)}</div>
                <Bubble teams={bubble} ctx={ctx} />
              </section>
            ))}
            <div className="mx-auto w-full max-w-xs">{sbBox}</div>
          </div>
        )}
      </div>
    </div>
  )
}
