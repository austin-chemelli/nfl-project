/**
 * The projected playoff bracket (Austin, 2026-11-12): the Playoff odds tab's default view. One plausible
 * field and path from the simulated odds (`bracket.ts`); every team shows its chance to reach that round.
 * Wide screens put AFC and NFC side by side with the Super Bowl below; phones stack them.
 */
import type { LeagueFile, LeagueTeam } from '../../data/contract'
import { TeamLink } from '../../components/TeamLink'
import { teamDotVars } from '../../lib/teamColors'
import { teamInfo } from '../../lib/teams'
import { projectConference, projectSeeds, superBowl, type ConfBracket, type Game, type OddsMap, type Seeded } from './bracket'
import { Move } from './Move'
import { fmtProb, recordOf, type Conf } from './playoffs'

/** The round a game's winner reaches: each number is the chance to win that game's round. */
type Round = 'div' | 'conf' | 'sb' | 'champ'
const value = (odds: OddsMap, team: string, r: Round | 'playoffs') => (r === 'playoffs' ? odds[team]?.playoffs : odds[team]?.rounds[r]) ?? 0

type Ctx = { odds: OddsMap; was?: OddsMap; standings: Map<string, LeagueTeam> }

function TeamLine({ s, round, ctx, state }: { s: Seeded; round: Round; ctx: Ctx; state: 'win' | 'lose' | 'plain' }) {
  const st = ctx.standings.get(s.team)
  const v = value(ctx.odds, s.team, round)
  return (
    <div
      data-matchup
      data-team={s.team}
      style={teamDotVars(s.team)}
      title={`${teamInfo(s.team).name}: ${fmtProb(v)} to ${round === 'champ' ? 'win the Super Bowl' : `reach the ${ROUND_NAME[round]}`}`}
      className={`flex min-w-0 items-center gap-1 px-1.5 py-1 text-[12px] sm:gap-1.5 sm:px-2 sm:text-[13px] ${state === 'lose' ? 'text-ink-3' : 'text-ink'}`}
    >
      <span className="tabular w-3 shrink-0 text-right text-[11px] text-ink-3">{s.seed}</span>
      <span aria-hidden className={`hidden h-2.5 w-2.5 shrink-0 rounded-full sm:inline-block ${state === 'lose' ? 'opacity-50' : ''}`} style={{ background: 'var(--team-home)' }} />
      <TeamLink team={s.team} className={`${state === 'win' ? 'font-semibold' : 'font-medium'} ${state === 'lose' ? 'text-ink-3' : ''}`}>
        {s.team}
      </TeamLink>
      {st && <span className="tabular hidden text-[11px] text-ink-3 sm:inline">{recordOf(st)}</span>}
      <span className="ml-auto flex shrink-0 items-center">
        <span className={`tabular ${state === 'win' ? 'font-semibold' : ''}`}>{fmtProb(v)}</span>
        {ctx.was && <Move from={value(ctx.was, s.team, round)} to={v} />}
      </span>
    </div>
  )
}

function GameBox({ g, round, ctx }: { g: Game; round: Round; ctx: Ctx }) {
  return (
    <div className="divide-y divide-[var(--border)] overflow-hidden rounded-md border border-line bg-surface-1">
      {[g.a, g.b].map((s) => (
        <div key={s.team} className={s === g.winner ? 'border-l-[3px] border-l-[var(--accent)]' : 'border-l-[3px] border-l-transparent'}>
          <TeamLine s={s} round={round} ctx={ctx} state={s === g.winner ? 'win' : 'lose'} />
        </div>
      ))}
    </div>
  )
}

function ByeBox({ s, ctx }: { s: Seeded; ctx: Ctx }) {
  return (
    <div className="overflow-hidden rounded-md border border-dashed border-line bg-surface-1">
      <div className="border-l-[3px] border-l-[var(--accent)]">
        <TeamLine s={s} round="div" ctx={ctx} state="win" />
      </div>
      <div className="px-2 pb-1 text-[11px] text-ink-3">Bye</div>
    </div>
  )
}

const COLS = ['Wild card', 'Divisional', 'Conference'] as const
const ROUND_NAME: Record<Round, string> = { div: 'divisional round', conf: 'conference game', sb: 'Super Bowl', champ: 'title' }

function Column({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col">
      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ink-3">{title}</div>
      <div className="flex flex-1 flex-col justify-around gap-2">{children}</div>
    </div>
  )
}

function ConfView({ conf, b, ctx, bubble }: { conf: Conf; b: ConfBracket; ctx: Ctx; bubble: string[] }) {
  return (
    <section aria-label={`${conf} projected bracket`} className="flex min-w-0 flex-col gap-2">
      <h3 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
        <span aria-hidden className="inline-block h-3 w-1 rounded-sm" style={{ background: `var(--conf-${conf.toLowerCase()})` }} />
        {conf}
      </h3>
      <div className="grid grid-cols-3 gap-1.5 sm:gap-3">
        <Column title={COLS[0]}>
          {b.bye.map((s) => <ByeBox key={s.team} s={s} ctx={ctx} />)}
          {b.wildCard.map((g) => <GameBox key={g.a.team} g={g} round="div" ctx={ctx} />)}
        </Column>
        <Column title={COLS[1]}>
          {b.divisional.map((g) => <GameBox key={g.a.team} g={g} round="conf" ctx={ctx} />)}
        </Column>
        <Column title={COLS[2]}>
          <GameBox g={b.conference} round="sb" ctx={ctx} />
        </Column>
      </div>
      {bubble.length > 0 && (
        <p className="tabular text-[12px] text-ink-3">
          Next in line: {bubble.map((t) => `${t} ${fmtProb(value(ctx.odds, t, 'playoffs'))}`).join(' · ')}
        </p>
      )}
    </section>
  )
}

export function Bracket({ file, odds, was, wide, first = 'AFC' }: { file: LeagueFile; odds: OddsMap; was?: OddsMap; wide: boolean; first?: Conf }) {
  const standings = new Map(file.teams.map((t) => [t.team, t]))
  const ctx: Ctx = { odds, was, standings }
  const confs = (['AFC', 'NFC'] as Conf[]).map((conf) => {
    const teams = file.teams.filter((t) => t.conf === conf && odds[t.team]).map((t) => t.team).sort((a, b) => odds[b].playoffs - odds[a].playoffs || a.localeCompare(b))
    const seeds = projectSeeds(teams, odds)
    const b = projectConference(seeds, odds)
    const bubble = teams.filter((t) => !seeds.includes(t)).slice(0, 3)
    return { conf, b, bubble }
  })
  const sb = superBowl(confs[0].b.champ, confs[1].b.champ, odds)
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div className={`grid gap-6 ${wide ? 'xl:grid-cols-2' : ''}`}>
        {(first === 'NFC' ? [...confs].reverse() : confs).map(({ conf, b, bubble }) => <ConfView key={conf} conf={conf} b={b} ctx={ctx} bubble={bubble} />)}
      </div>
      <section aria-label="Projected Super Bowl" className="mx-auto flex w-full max-w-md flex-col gap-1">
        <div className="text-center text-[11px] font-medium uppercase tracking-wide text-ink-3">Super Bowl</div>
        <GameBox g={{ a: sb.afc, b: sb.nfc, winner: sb.winner }} round="champ" ctx={ctx} />
        <div className="mt-1 text-center text-[13px] text-ink-2">
          Projected champion: <span className="font-semibold text-ink">{teamInfo(sb.winner.team).name}</span>
        </div>
      </section>
    </div>
  )
}
