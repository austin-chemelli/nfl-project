/**
 * What the market tends to miss here (ADR 0028, M25.5c / M25.6): the ledger's `use` candidates against the
 * market's spread, as a lean in points toward one team with its 90% range, the candidates behind it, and the
 * live record since tracking began. Context, never a pick: it never reaches a line, the scorecard or the
 * README. Every number is read from the JSON (`lean`, `tracker.leans`).
 */
import { Section } from '../../components/ui'
import type { Game, LeansRecord } from '../../data/contract'
import { useTracker } from '../../data/api'

const fmt = (x: number) => String(Math.abs(x))

/** -x..x points around the market's line (0): away to the left, home to the right. */
function RangeBar({ pts, lo, hi, home, away }: { pts: number; lo: number; hi: number; home: string; away: string }) {
  const span = Math.max(1.5, Math.abs(lo), Math.abs(hi), Math.abs(pts)) * 1.15
  const at = (v: number) => `${50 + (v / span) * 50}%`
  const color = pts >= 0 ? 'var(--team-home)' : 'var(--team-away)'
  return (
    <div className="mt-2" role="img" aria-label={`lean ${fmt(pts)} points toward ${pts >= 0 ? home : away}, 90% range ${lo} to ${hi} points toward ${home}`}>
      <div className="relative h-6">
        <span className="absolute left-0 right-0 top-[11px] h-[2px] rounded" style={{ background: 'var(--band)' }} />
        <span className="absolute top-[4px] h-4 w-[2px] -translate-x-1/2" style={{ left: '50%', background: 'var(--text-muted)' }} />
        <span className="absolute top-[9px] h-[6px] rounded" style={{ left: at(Math.min(lo, hi)), width: `calc(${at(Math.max(lo, hi))} - ${at(Math.min(lo, hi))})`, background: color, opacity: 0.35 }} />
        <span className="absolute top-[5px] h-[14px] w-[14px] -translate-x-1/2 rounded-full" style={{ left: at(pts), background: color }} />
      </div>
      <div className="flex justify-between text-[11px] text-ink-3">
        <span>← toward {away}</span>
        <span>the market's line</span>
        <span>toward {home} →</span>
      </div>
    </div>
  )
}

function Record({ r }: { r: LeansRecord | null | undefined }) {
  if (!r) return null
  return (
    <p data-testid="lean-record" className="m-0 mt-3 text-[12.5px] text-ink-2">
      Tracked since {r.from_season} Week {r.from_week}:{' '}
      {r.n === 0 ? 'no finished games yet' : `${r.right} right, ${r.wrong} wrong${r.push ? `, ${r.push} push${r.push === 1 ? '' : 'es'}` : ''} against the spread`}
      {` · a typical lean is ${r.mean_abs_pts} points.`}
    </p>
  )
}

const GRADE: Record<string, string> = { right: 'Landed on the lean’s side of the spread', wrong: 'Landed on the other side of the spread', push: 'Landed on the number' }

export function LeanBlock({ g }: { g: Game }) {
  const tracker = useTracker()
  const l = g.lean
  if (!l) return null
  const toward = l.pts >= 0 ? g.home : g.away
  const sign = l.pts >= 0 ? 1 : -1
  const [a, b] = [l.lo * sign, l.hi * sign].sort((x, y) => x - y)
  const range = `${a < 0 ? `${fmt(a)} toward ${l.pts >= 0 ? g.away : g.home}` : fmt(a)} to ${fmt(b)}`
  return (
    <Section
      title="What the market tends to miss here"
      help="Stats that have, since 2006, predicted how far the final margin lands from the market's spread (the candidates the ledger marked 'use'). Each one's slope times this game's gap, added up. Context, not a pick: it never feeds a forecast."
    >
      <div data-testid="lean" className="rounded-lg border border-line bg-surface-1 p-3">
        <p className="m-0 text-[14px]">
          History leans <b>{toward}</b> by <b className="tabular">{fmt(l.pts)}</b> points against the market's spread{' '}
          <span className="text-ink-2">(90% range {range})</span>.
        </p>
        <RangeBar pts={l.pts} lo={l.lo} hi={l.hi} home={g.home} away={g.away} />
        <ul className="m-0 mt-2 list-none p-0 text-[13px]">
          {l.parts.map((p) => (
            <li key={p.candidate} data-testid={`lean-part-${p.candidate}`} className="flex items-baseline justify-between gap-3 border-b border-line py-1">
              <span className="min-w-0 truncate text-ink-2">{p.label}</span>
              <span className="tabular shrink-0">
                {fmt(p.pts)} toward {p.pts >= 0 ? g.home : g.away}
              </span>
            </li>
          ))}
        </ul>
        {l.grade && <p data-testid="lean-grade" data-grade={l.grade} className={`m-0 mt-2 text-[13px] ${l.grade === 'right' ? 'text-[var(--good)]' : l.grade === 'wrong' ? 'text-[var(--critical)]' : 'text-ink-2'}`}>{GRADE[l.grade]}.</p>}
        <Record r={tracker.data?.leans} />
        <p className="m-0 mt-1 text-[11.5px] text-ink-3">The stats overlap, so the range is wide on purpose. Not betting advice.</p>
      </div>
    </Section>
  )
}
