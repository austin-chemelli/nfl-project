import { LinePath, type PathPoint } from '../../charts'
import { Section } from '../../components/ui'
import type { Game } from '../../data/contract'
import { HEADLINE, SHORT } from '../../lib/models'
import { pick } from '../../lib/format'
import { etStamp, fmtPts, pathSentence, windowWords } from './line'

const ms = (iso: string) => new Date(iso).getTime()

/** How the market line moved before kickoff, and what changed in the same windows (ADR 0024). */
export function TheLine({ g }: { g: Game }) {
  const pts = g.market_history
  const m = g.line_move
  if (pts.length < 2 || !m) {
    return (
      <Section title="How the line moved">
        <p className="text-ink-2">{pts.length === 1 ? 'We have one snapshot of this game so far; movement shows from the second.' : 'No market line for this game in our snapshots yet.'}</p>
      </Section>
    )
  }
  const ends = [ms(pts[pts.length - 1].ts), ...(m.lock_ts ? [ms(m.lock_ts)] : []), ...g.market_events.map((e) => ms(e.ts))]
  const domain: [number, number] = [Math.min(ms(pts[0].ts), ...g.market_events.map((e) => ms(e.ts))), Math.max(...ends)]
  const series = (k: 'spread_home' | 'total'): PathPoint[] => pts.map((p) => ({ t: ms(p.ts), v: p[k], note: `${etStamp(p.ts)} · ${p.n_books} books` }))
  const marks = m.lock_ts ? [{ t: ms(m.lock_ts), label: 'Locked' }] : []
  const events = g.market_events.filter((e) => e.kind !== 'lock')
  // events at the same moment share a number, so their marks don't sit on top of each other
  const times = [...new Set(events.map((e) => e.ts))]
  const num = (ts: string) => times.indexOf(ts) + 1
  const evMarks = times.map((ts) => ({ t: ms(ts), n: num(ts) }))
  const path = pathSentence(pts, g.home, g.away)
  const sinceLock = windowWords(m.since_lock?.spread_home, g.home, g.away)
  const lastDay = windowWords(m.last_day?.spread_home, g.home, g.away)
  return (
    <Section title="How the line moved" help="The consensus across sportsbooks at each of our snapshots before kickoff: the median spread and total, needing at least three books.">
      <TodayLine g={g} />
      <p className="m-0 text-ink">
        Since we first saw it ({etStamp(m.first_seen)}): {path ?? 'no change'}.
        {sinceLock && <> Since the lock: {sinceLock}.</>}
        {lastDay && <> Last day: {lastDay}.</>}
      </p>
      <div className="mt-3 flex flex-col gap-2">
        <LinePath points={series('spread_home')} marks={marks} events={evMarks} domain={domain} label="Spread"
          format={(v) => (Math.abs(v) < 0.25 ? 'even' : `${v > 0 ? g.home : g.away} −${fmtPts(Math.abs(v))}`)} up={`toward ${g.home}`} down={`toward ${g.away}`} />
        <LinePath points={series('total')} marks={marks} events={evMarks} domain={domain} label="Total" format={fmtPts} up="higher" down="lower" />
      </div>
      {events.length > 0 && (
        <div className="mt-3">
          <h3 className="text-[13px] font-medium text-ink">In the same windows</h3>
          <ol className="mt-1 flex list-none flex-col gap-1.5 p-0 text-[13px]">
            {events.map((e, i) => (
              <li key={`${e.ts}-${i}`} className="flex gap-2">
                <span aria-hidden className="tabular inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-[var(--text-muted)] bg-surface-2 text-[9px]">{num(e.ts)}</span>
                <span className="min-w-0 break-words">
                  <span className="text-ink-3">{etStamp(e.ts)} · </span>
                  {e.text}
                  {e.source_url && <> <a href={e.source_url} target="_blank" rel="noopener noreferrer">source</a></>}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Section>
  )
}

/** The headline line as locked beside today's preview score: whether we moved with the market. */
function TodayLine({ g }: { g: Game }) {
  const t = g.today?.models[HEADLINE]
  if (!g.today || t?.p_home == null || g.result) return null
  const locked = g.models[HEADLINE]
  const name = `The ${SHORT[HEADLINE]}`
  const now = pick(t.p_home, g.home, g.away)
  return (
    <p className="m-0 mb-2 text-[14px] text-ink-2">
      {locked?.status === 'locked' && locked.p_home != null ? (
        <>{name} locked {pick(locked.p_home, g.home, g.away)}; on the data as of {etStamp(g.today.scored_at)} it reads {now}.</>
      ) : (
        <>On the data as of {etStamp(g.today.scored_at)}, the {SHORT[HEADLINE]} reads {now}.</>
      )}{' '}
      <span className="text-ink-3">A preview, not locked, and never graded.</span>
    </p>
  )
}

