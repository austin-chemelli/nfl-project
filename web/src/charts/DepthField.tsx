/**
 * A team's full-strength lineup (M24.7 round 3): offense and defense as name cards in formation rows
 * (the line, then the backfield or the second level, receivers and corners on the outside). Three
 * cues only: a key player's card is shaded in the team color; a starter who won't play has a red
 * status line and the man who plays instead under it; a Questionable, Doubtful or hurt-in-practice
 * starter has an amber one. No player values. Hover a card for the return window and the chart
 * behind him. On a phone the same lineup reads as room cards. The color is the team's
 * (`--team-home`/`--team-away` under `[data-matchup]`) or the accent on the team page.
 */
import type { HealthStarter } from '../data/contract'
import { GROUP, GROUP_ORDER, lastName, stepsIn, tone, whenBack, type Tone } from '../lib/health'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'

type Layout = { left: string[][]; center: string[][]; right: string[][] }

// rows top (the line of scrimmage) to bottom; slots not listed go to a last center row
const LAYOUT: Record<'offense' | 'defense', Layout> = {
  offense: { left: [['WR1'], ['WR3']], center: [['LT', 'LG', 'C', 'RG', 'RT', 'TE'], ['QB'], ['RB']], right: [['WR2']] },
  defense: {
    left: [['LCB']],
    center: [['LDE', 'LDT', 'NT', 'RDT', 'RDE'], ['WLB', 'LILB', 'MLB', 'RILB', 'SLB'], ['SS', 'FS']],
    right: [['RCB']],
  },
}

const DOT: Record<Tone, string | null> = { out: 'var(--critical)', iffy: 'var(--warning)', doubt: 'var(--warning)', in: null }

/** The status line on a card: "IR · Wk 15" (back that week at the earliest), "Out", "Questionable", "No practice". */
function shortStatus(s: HealthStarter, week: number): string | null {
  if (!s.status) return null
  if (s.reserve) {
    const kind = s.status.startsWith('PUP') ? 'PUP' : s.status.startsWith('IR') ? 'IR' : 'Reserve'
    if (s.eligible_week == null) return kind
    return s.eligible_week <= week ? `${kind} · eligible` : `${kind} · Wk ${s.eligible_week}`
  }
  if (s.doubt) return s.status === 'Did not practice' ? 'No practice' : 'Limited'
  return s.status
}

const keyStyle = (color: string) => ({
  background: `color-mix(in srgb, ${color} 16%, var(--surface-1))`,
  borderColor: `color-mix(in srgb, ${color} 55%, transparent)`,
})

function Card({ s, week, color, bind }: { s: HealthStarter; week: number; color: string; bind: ReturnType<typeof useChartTip>['bind'] }) {
  const t = tone(s)
  const status = shortStatus(s, week)
  const sub = t === 'out' || t === 'iffy' ? stepsIn(s) : null
  return (
    <div
      {...bind(s.slot)}
      data-slot={s.slot}
      data-tone={t}
      data-key={s.key || undefined}
      aria-label={label(s, week)}
      className="w-[6.25rem] shrink-0 rounded-md border border-line bg-[var(--surface-1)] px-1.5 py-1 text-center leading-tight"
      style={{ ...bind(s.slot).style, ...(s.key ? keyStyle(color) : {}) }}
    >
      <div className="text-[10px] font-medium uppercase tracking-wide text-ink-3">{s.slot.replace(/[123]$/, '')}</div>
      <div className={`break-words text-[13px] ${s.key ? 'font-semibold' : ''} ${t === 'out' ? 'text-ink-3' : 'text-ink'}`}>{lastName(s.player)}</div>
      {status && (
        <div className="mt-0.5 flex items-center justify-center gap-1 text-[11px] text-ink-2">
          <span aria-hidden className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: DOT[t] ?? 'var(--text-muted)' }} />
          <span className="truncate">{status}</span>
        </div>
      )}
      {sub && <div className="truncate text-[11px] font-medium text-ink">→ {lastName(sub)}</div>}
    </div>
  )
}

function label(s: HealthStarter, week: number) {
  const st = s.status ? `, ${whenBack(s, week)}` : ''
  const sub = s.status && stepsIn(s) ? `; ${stepsIn(s)} plays instead` : ''
  return `${s.slot}: ${s.player}${s.key ? ', key player' : ''}${st}${sub}`
}

function Tip({ s, week }: { s: HealthStarter; week: number }) {
  const t = tone(s)
  return (
    <>
      <TipTitle note={`${s.slot.replace(/[123]$/, '')}${s.grp ? ` · ${GROUP[s.grp] ?? s.grp}` : ''}${s.key ? ' · key player' : ''}`}>{s.player}</TipTitle>
      {s.status ? <TipRow color={DOT[t] ?? undefined} value={whenBack(s, week)} label="" /> : <div className="text-ink-2">Available: not on a reserve list or this week&apos;s report.</div>}
      {t === 'iffy' && <TipRow value={`${Math.round(100 * s.p_play)}%`} label={`of players listed ${s.status} have played`} />}
      {t === 'doubt' && <TipNote>Hurt in practice; no game status until Friday.</TipNote>}
      {s.depth.length > 0 && <TipRow value={s.depth.map((d) => d.player + (d.status ? ` (${d.status})` : '')).join(', then ')} label="behind him" />}
      {s.depth.length === 0 && s.replaced_by && <TipRow value={s.replaced_by} label="playing instead" />}
    </>
  )
}

function Unit({ unit, spots, color, week }: { unit: 'offense' | 'defense'; spots: HealthStarter[]; color: string; week: number }) {
  const { box, at, bind, card } = useChartTip()
  const hovered = spots.find((s) => s.slot === at?.key)
  const by = new Map(spots.map((s) => [s.slot, s]))
  const layout = LAYOUT[unit]
  const placed = new Set([...layout.left, ...layout.center, ...layout.right].flat())
  const extra = spots.filter((s) => !placed.has(s.slot)).map((s) => s.slot)
  const rows = (rs: string[][]) =>
    rs.map((r) => r.filter((k) => by.has(k))).filter((r) => r.length > 0).map((r) => (
      <div key={r.join()} className="flex items-start justify-center gap-1.5">
        {r.map((k) => <Card key={k} s={by.get(k)!} week={week} color={color} bind={bind} />)}
      </div>
    ))
  return (
    <figure className="m-0 min-w-0">
      <figcaption className="mb-1 text-[12px] font-medium uppercase tracking-wide text-ink-3">{unit === 'offense' ? 'Offense' : 'Defense'}</figcaption>
      <div ref={box} className="relative rounded-lg bg-[var(--surface-2)] px-2 pb-3 pt-2.5" role="group" aria-label={`${unit}: full-strength starters`}>
        <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-2">
          <div className="flex flex-col gap-3">{rows(layout.left)}</div>
          <div className="flex flex-col gap-3">{rows([...layout.center, extra])}</div>
          <div className="flex flex-col gap-3">{rows(layout.right)}</div>
        </div>
        {hovered && card(<Tip s={hovered} week={week} />)}
      </div>
    </figure>
  )
}

/** The phone layout: one card per position room. */
function Rooms({ starters, week, color }: { starters: HealthStarter[]; week: number; color: string }) {
  const groups = GROUP_ORDER.filter((g) => starters.some((s) => s.grp === g))
  return (
    <div className="grid gap-2">
      {groups.map((g) => {
        const rows = starters.filter((s) => s.grp === g)
        const out = rows.filter((s) => tone(s) !== 'in').length
        return (
          <section key={g} className="rounded-md border border-line bg-[var(--surface-1)] px-3 py-2" data-room={g}>
            <h5 className="m-0 flex justify-between text-[13px] font-medium text-ink-2">
              <span>{GROUP[g] ?? g}</span>
              {out > 0 && <span className="text-ink-3">{out} of {rows.length} out or in doubt</span>}
            </h5>
            <ul className="m-0 mt-1 flex list-none flex-col gap-1 p-0 text-[14px]">
              {rows.map((s) => {
                const t = tone(s)
                const sub = t === 'out' || t === 'iffy' ? stepsIn(s) : null
                return (
                  <li key={s.slot} data-slot={s.slot}>
                    <span className="inline-block w-10 text-[12px] text-ink-3">{s.slot.replace(/[123]$/, '')}</span>
                    <span className={`rounded px-1 ${s.key ? 'font-semibold' : ''} ${t === 'out' ? 'text-ink-3' : 'text-ink'}`} style={s.key ? keyStyle(color) : undefined}>{s.player}</span>
                    {s.status && (
                      <span className="flex items-center gap-1 pl-10 text-[13px] text-ink-2">
                        <span aria-hidden className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: DOT[t] ?? 'var(--text-muted)' }} />
                        {whenBack(s, week)}{sub ? ` → ${sub}` : ''}
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

export function DepthField({ starters, week, color = 'var(--accent)', testId = 'depth-field' }: { starters: HealthStarter[]; week: number; color?: string; testId?: string }) {
  const units = (['offense', 'defense'] as const).map((u) => [u, starters.filter((s) => s.unit === u)] as const).filter(([, rows]) => rows.length > 0)
  return (
    <div data-testid={testId}>
      <div className="hidden max-w-[880px] gap-4 md:grid" data-view="field">
        {units.map(([u, rows]) => <Unit key={u} unit={u} spots={rows} color={color} week={week} />)}
      </div>
      <div className="md:hidden" data-view="rooms">
        <Rooms starters={starters} week={week} color={color} />
      </div>
    </div>
  )
}

/** The key under the lineup, once per page. */
export function DepthFieldKey({ color = 'var(--accent)' }: { color?: string }) {
  const dot = (c: string) => <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: c }} />
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-3">
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-3 w-5 rounded-sm border" style={keyStyle(color)} />
        key player
      </span>
      <span className="inline-flex items-center gap-1.5">{dot('var(--critical)')} out, with who plays instead (→)</span>
      <span className="inline-flex items-center gap-1.5">{dot('var(--warning)')} questionable, doubtful or hurt in practice</span>
      <span>IR · Wk 15: can return in Week 15 at the earliest</span>
    </div>
  )
}
