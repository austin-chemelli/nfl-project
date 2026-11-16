/**
 * The official injury report on the Health tab (Austin 2026-11-15: "messy"): one block per team, then
 * by status (Out and Doubtful, then Questionable), key players first, one line per player (name,
 * position, key, injury, last practice) instead of a five-column table, so it reads on a 375 px phone.
 * Full-strength starters on a reserve list (IR, PUP), who aren't on the weekly report, close each team's
 * block on one line. Everything is read from `injuries` and `health`.
 */
import type { Game, HealthStarter } from '../../data/contract'
import { injuryRank, sortInjuries } from './helpers'

type Inj = Game['injuries'][number]

const PRACTICE: [RegExp, string][] = [[/did not/i, 'no practice'], [/limited/i, 'limited'], [/full/i, 'full practice']]
const practice = (p: string | null) => (p ? (PRACTICE.find(([re]) => re.test(p))?.[1] ?? p.toLowerCase()) : null)

const GROUPS = [
  { label: 'Out or doubtful', test: (i: Inj) => injuryRank(i.status) <= 1, tone: 'var(--critical)' },
  { label: 'Questionable', test: (i: Inj) => injuryRank(i.status) === 2, tone: 'var(--warning)' },
]

function Line({ i, isKey }: { i: Inj; isKey: boolean }) {
  const extra = [i.status !== 'Out' && injuryRank(i.status) === 1 ? i.status : null, i.injury?.toLowerCase(), practice(i.practice)].filter(Boolean)
  return (
    <li className="flex flex-wrap items-baseline gap-x-1.5 border-b border-line py-1 text-[13px]" data-key={isKey || undefined}>
      <span className="font-medium text-ink">{i.player}</span>
      {i.pos && <span className="text-ink-3">{i.pos}</span>}
      {isKey && <span className="rounded border border-[var(--text-muted)] px-1 text-[10px] uppercase tracking-wide text-ink-2">key</span>}
      {extra.length > 0 && <span className="text-ink-3">· {extra.join(' · ')}</span>}
    </li>
  )
}

export function InjuryReport({ g }: { g: Game }) {
  const sides = [['away', g.away], ['home', g.home]] as const
  return (
    <div data-testid="injury-report" className="grid gap-6 md:grid-cols-2">
      {sides.map(([side, team]) => {
        const starters: HealthStarter[] = g.health?.[side]?.starters ?? []
        const keyIds = new Set(starters.filter((s) => s.key && s.gsis_id).map((s) => s.gsis_id))
        const isKey = (i: Inj) => Boolean(i.gsis_id && keyIds.has(i.gsis_id))
        const rows = g.injuries.filter((i) => i.team === team)
        const reserve = starters.filter((s) => s.reserve).sort((a, b) => Number(b.key) - Number(a.key))
        return (
          <div key={team} className="min-w-0" data-testid={`report-${team}`}>
            <h4 className="m-0 mb-1 flex items-center gap-2 text-[14px] font-semibold">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ background: `var(--team-${side})` }} />
              {team}
            </h4>
            {rows.length === 0 && (
              <p className="m-0 text-[13px] text-ink-2">
                {g.injuries.length === 0 ? 'No game statuses on the official report yet (practice-only reports aren’t listed here).' : 'None listed with a game status.'}
              </p>
            )}
            {GROUPS.map(({ label, test, tone }) => {
              const grp = sortInjuries(rows.filter(test)).sort((a, b) => Number(isKey(b)) - Number(isKey(a)))
              if (grp.length === 0) return null
              return (
                <div key={label} className="mt-2">
                  <div className="text-[12px] font-semibold" style={{ color: tone }}>{label}</div>
                  <ul className="m-0 list-none p-0">{grp.map((i) => <Line key={`${i.player}-${i.status}`} i={i} isKey={isKey(i)} />)}</ul>
                </div>
              )
            })}
            {reserve.length > 0 && (
              <p className="m-0 mt-2 text-[12px] text-ink-3" data-testid={`reserve-${team}`}>
                Starters on reserve lists:{' '}
                {reserve.map((s, n) => (
                  <span key={s.slot}>
                    {n > 0 && ', '}
                    <span className="font-medium text-ink-2">{s.player}</span> {s.slot.replace(/[123]$/, '')}{s.key ? ' (key)' : ''} · {s.status}
                  </span>
                ))}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
