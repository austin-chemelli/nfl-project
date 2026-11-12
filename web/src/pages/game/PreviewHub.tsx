/**
 * The game's Preview, meant to stand on its own (Austin, 2026-11-12; plan game-preview-hub): "Who has the
 * edge" in full, where each team has the edge (both cards in full), the key news from the injury report and
 * the week's research, then the line and the tale of the tape side by side. Each section links to its tab for
 * the deeper view. A section hides when there is nothing for it yet. Every number is read from the JSON; this
 * file only picks and places.
 */
import type { ReactNode } from 'react'
import { useSetTab } from '../../components/Tabs'
import { EdgeCard } from '../../components/EdgeCard'
import { Section } from '../../components/ui'
import type { Game, Meta, Narrative } from '../../data/contract'
import { spreadLabel } from '../../lib/format'
import { dayOf, impactMarker, QB_STATUS, sortInjuries, sortMatchupNotes, sortNotes, tape } from './helpers'
import { topAbsence } from './summary'
import { hasLine } from './TheLine'
import { disagrees } from './books'
import { Preview } from './Preview'

function More({ tab, children }: { tab: string; children: ReactNode }) {
  const setTab = useSetTab()
  return (
    <button type="button" onClick={() => setTab(tab)} className="cursor-pointer whitespace-nowrap border-0 bg-transparent p-0 text-[13px] text-accent hover:underline">
      {children} →
    </button>
  )
}

function Card({ title, tab, more, children, testid }: { title: string; tab: string; more: string; children: ReactNode; testid: string }) {
  return (
    <section data-testid={testid} className="flex min-w-0 flex-col rounded-lg border border-line bg-surface-1 px-4 py-3">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="m-0 text-[15px] font-semibold">{title}</h3>
        <More tab={tab}>{more}</More>
      </div>
      {children}
    </section>
  )
}

const colorFor = (g: Game) => (team: string) => (team === g.home ? 'var(--team-home)' : team === g.away ? 'var(--team-away)' : 'var(--text-secondary)')

export function EdgeCardsSection({ g }: { g: Game }) {
  const sides = g.edge_cards ?? []
  if (sides.length === 0) return null
  return (
    <Section
      title="Where each team has the edge"
      help="The battles where one team's unit ranks well and the other's matching unit ranks poorly, and how often teams in that spot won when they won that battle."
      aside={<More tab="tendencies">Unit ranks and habits</More>}
    >
      {g.matchups?.lede && <p className="mb-4 mt-0 max-w-3xl text-[14px] text-ink">{g.matchups.lede}</p>}
      <div className="flex flex-col gap-8" data-testid="edge-cards">
        {sides.map((s) => (
          <EdgeCard key={s.team} side={s} colorOf={colorFor(g)} />
        ))}
      </div>
    </Section>
  )
}

const firstSentences = (t: string, n: number) => (t.match(new RegExp(`^(?:.*?[.!?](?:\\s|$)){1,${n}}`))?.[0] ?? t).trim()

const NOTES_PER_TEAM = 2
const ABSENCES_PER_TEAM = 3

function TeamNews({ g, team, t }: { g: Game; team: string; t: Narrative['home'] | null }) {
  const out = sortInjuries(g.injuries.filter((i) => i.team === team && topAbsence([i]) != null))
  const shown = out.slice(0, ABSENCES_PER_TEAM)
  const notes = t ? sortNotes(t.notes).filter((n) => n.impact !== 0).slice(0, NOTES_PER_TEAM) : []
  const qbFlag = t && t.qb_status > 0 ? `${t.qb_name ?? 'QB'}: ${QB_STATUS[t.qb_status] ?? t.qb_status}` : null
  return (
    <div data-testid={`news-${team}`} className="min-w-0">
      <h4 className="m-0 mb-1.5 flex items-center gap-2 text-[14px] font-semibold">
        <span className="inline-block h-3 w-3 rounded-sm" style={{ background: colorFor(g)(team) }} />
        {team}
      </h4>
      {qbFlag && <p className="m-0 mb-1 text-[13px] font-medium text-[var(--warning)]">{qbFlag}</p>}
      {shown.length > 0 ? (
        <ul className="m-0 mb-2 flex list-none flex-wrap gap-1.5 p-0" aria-label={`${team} out or doubtful`}>
          {shown.map((i) => (
            <li key={i.player} className="rounded-full border border-line px-2 py-0.5 text-[12px]">
              <b>{i.player}</b>
              <span className="text-ink-2">
                {i.pos ? ` ${i.pos}` : ''} · {i.status.toLowerCase()}
              </span>
            </li>
          ))}
          {out.length > shown.length && <li className="px-1 py-0.5 text-[12px] text-ink-3">+{out.length - shown.length} more</li>}
        </ul>
      ) : (
        <p className="m-0 mb-2 text-[12.5px] text-ink-3">{g.injuries.length ? 'No one out or doubtful.' : 'No official report yet.'}</p>
      )}
      {notes.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          {notes.map((n) => {
            const m = impactMarker(n.impact)
            return (
              <li key={n.text} className="text-[13px] leading-snug">
                <span aria-label={m.words} className="mr-1 whitespace-nowrap font-medium" style={{ color: n.impact > 0 ? 'var(--good)' : 'var(--critical)' }}>
                  {m.arrows}
                </span>
                {n.text}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export function NewsSection({ g }: { g: Game }) {
  const n = g.narrative
  if (!n && g.injuries.length === 0) return null
  const top = n ? sortMatchupNotes(n.matchup_notes)[0] : null
  return (
    <Section
      title="Key news"
      help="The biggest absences from the official injury report, and the notes from this week's research that matter most for each team (▲ helps, ▼ hurts). The full report, with every source, is on the Injuries & news tab."
      aside={<More tab="news">Full report and sources</More>}
    >
      <div data-testid="teaser-news" className="flex flex-col gap-3">
        {n?.consensus_narrative && <p className="m-0 max-w-3xl text-[14px]">{firstSentences(n.consensus_narrative, 2)}</p>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TeamNews g={g} team={g.away} t={n?.away ?? null} />
          <TeamNews g={g} team={g.home} t={n?.home ?? null} />
        </div>
        {top && (
          <p className="m-0 max-w-3xl border-l-[3px] border-line pl-3 text-[13px] text-ink-2">
            <span className="font-medium text-ink">The most-cited matchup:</span> {top.text}
          </p>
        )}
        {n && <p className="m-0 text-[11.5px] text-ink-3">From research as of {dayOf(n.known_as_of)}. It never feeds the probabilities.</p>}
      </div>
    </Section>
  )
}

/**
 * One number's move as a strip: a hollow dot where it was first seen, a filled dot where it is now, an arrow
 * between, each labelled. Unchanged is one dot. The strip spans the two values plus a point either side.
 */
function MoveRow({ label, from, to, fmt, color, testid }: { label: string; from: number; to: number; fmt: (v: number) => string; color: string; testid: string }) {
  const lo = Math.min(from, to) - 1
  const hi = Math.max(from, to) + 1
  const at = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`
  const moved = from !== to
  return (
    <div data-testid={testid} data-moved={moved ? 'yes' : 'no'} className="grid grid-cols-[3.5rem_minmax(0,1fr)] items-center gap-3">
      <span className="text-[12px] text-ink-2">{label}</span>
      <div className="relative h-11" role="img" aria-label={moved ? `${label}: ${fmt(from)} when first seen, ${fmt(to)} now` : `${label}: ${fmt(to)}, unchanged`}>
        <span className="absolute left-0 right-0 top-[21px] h-[2px] rounded" style={{ background: 'var(--band)' }} />
        {moved && (
          <span
            className="absolute top-[21px] h-[2px]"
            style={{ left: at(Math.min(from, to)), width: `calc(${at(Math.max(from, to))} - ${at(Math.min(from, to))})`, background: color, opacity: 0.6 }}
          />
        )}
        {moved && (
          <>
            <span className="absolute top-[16px] h-3 w-3 -translate-x-1/2 rounded-full border-2 bg-surface-1" style={{ left: at(from), borderColor: 'var(--text-muted)' }} />
            <span className="tabular absolute top-[30px] -translate-x-1/2 whitespace-nowrap text-[11px] text-ink-3" style={{ left: at(from) }}>
              {fmt(from)}
            </span>
          </>
        )}
        <span className="absolute top-[15px] h-[14px] w-[14px] -translate-x-1/2 rounded-full" style={{ left: at(to), background: color }} />
        <span className="tabular absolute top-0 -translate-x-1/2 whitespace-nowrap text-[12.5px] font-semibold" style={{ left: at(to) }}>
          {fmt(to)}
        </span>
      </div>
    </div>
  )
}

export function LineTeaser({ g }: { g: Game }) {
  if (!hasLine(g)) return null
  const h = g.market_history
  const first = h[0]
  const last = h[h.length - 1]
  const favColor = (s: number | null) => (s == null || Math.abs(s) < 0.25 ? 'var(--text-secondary)' : s > 0 ? 'var(--team-home)' : 'var(--team-away)')
  const spreadMoved = first.spread_home !== last.spread_home
  const totalMoved = first.total !== last.total
  return (
    <Card title="The line" tab="line" more="Movement and every book" testid="teaser-line">
      <div className="flex flex-col gap-1">
        {first.spread_home != null && last.spread_home != null && (
          <MoveRow label="Spread" from={first.spread_home} to={last.spread_home} fmt={(v) => spreadLabel(v, g.home, g.away)} color={favColor(last.spread_home)} testid="move-spread" />
        )}
        {first.total != null && last.total != null && <MoveRow label="Total" from={first.total} to={last.total} fmt={(v) => String(v)} color="var(--text-secondary)" testid="move-total" />}
      </div>
      <p className="m-0 mt-2 text-[12.5px] text-ink-2">
        {spreadMoved || totalMoved ? `Moved since first seen ${dayOf(first.ts)}` : `Unchanged since first seen ${dayOf(first.ts)}`}
        {' · '}
        {disagrees(g.books) ? <span className="text-[var(--warning)]">the books disagree</span> : last.n_books != null ? `${last.n_books} books agree` : ''}
      </p>
    </Card>
  )
}

const TOP_GAPS = 4

export function TapeTeaser({ g, meta }: { g: Game; meta: Meta }) {
  const rows = tape(g.features, meta)
    .flatMap((t) => t.groups.flatMap((x) => x.rows))
    .filter((r) => r.band)
    .map((r) => ({ r, gap: Math.abs(r.band!.homeV - r.band!.awayV) / (r.band!.q3 - r.band!.q1) }))
    .sort((a, b) => b.gap - a.gap)
    .slice(0, TOP_GAPS)
  if (rows.length === 0) return null
  return (
    <Card title="Tale of the tape" tab="details" more="Every stat" testid="teaser-tape">
      <p className="mb-1 mt-0 text-[12.5px] text-ink-2">Where the two teams sit furthest apart (bold is better):</p>
      <ul className="m-0 list-none p-0 text-[13px]">
        {rows.map(({ r }) => {
          const b = r.band!
          const homeBetter = b.flip ? b.homeV < b.awayV : b.homeV > b.awayV
          return (
            <li key={r.feature} data-testid={`gap-${r.feature}`} className="flex items-baseline justify-between gap-3 border-b border-line py-1">
              <span className="min-w-0 truncate" title={r.help}>
                {r.label}
              </span>
              <span className="tabular shrink-0 text-ink-2">
                <span className={!homeBetter ? 'font-semibold text-ink' : ''}>
                  {g.away} {r.away}
                </span>
                {' · '}
                <span className={homeBetter ? 'font-semibold text-ink' : ''}>
                  {g.home} {r.home}
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

export function PreviewHub({ g, meta }: { g: Game; meta: Meta }) {
  const line = hasLine(g)
  return (
    <div className="flex flex-col gap-10" data-testid="preview-hub">
      <Preview g={g} meta={meta} />
      <EdgeCardsSection g={g} />
      <NewsSection g={g} />
      <div className={`grid grid-cols-1 gap-4 ${line ? 'md:grid-cols-2' : ''}`}>
        <LineTeaser g={g} />
        <TapeTeaser g={g} meta={meta} />
      </div>
    </div>
  )
}
