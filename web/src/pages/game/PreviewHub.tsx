/**
 * The game's Preview as a preview of every tab (Austin, 2026-11-12; plan game-preview-hub): one card per
 * tab, in a fixed order, each with the tab's most notable item and a link into the tab for the rest. The
 * Preview alone should be enough; the tabs are for digging in. A card hides when its tab has nothing yet.
 * Every number is the tab's own, read from the same JSON; this file only picks and places.
 */
import type { ReactNode } from 'react'
import { useSetTab } from '../../components/Tabs'
import { EdgeCard } from '../../components/EdgeCard'
import { DivergingBars } from '../../charts'
import type { Game, Meta } from '../../data/contract'
import { ptsFor, spreadLabel } from '../../lib/format'
import { dayOf, previewRows, sortMatchupNotes, tape } from './helpers'
import { topAbsence } from './summary'
import { hasLine } from './TheLine'
import { disagrees } from './books'

function Card({ title, tab, more, children, testid }: { title: string; tab: string; more: string; children: ReactNode; testid: string }) {
  const setTab = useSetTab()
  return (
    <section data-testid={testid} className="rounded-lg border border-line bg-surface-1 px-4 py-3">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h2 className="m-0 text-[15px] font-semibold">{title}</h2>
        <button type="button" onClick={() => setTab(tab)} className="cursor-pointer whitespace-nowrap border-0 bg-transparent p-0 text-[12.5px] text-accent hover:underline">
          {more} →
        </button>
      </div>
      {children}
    </section>
  )
}

const colorFor = (g: Game) => (team: string) => (team === g.home ? 'var(--team-home)' : team === g.away ? 'var(--team-away)' : 'var(--text-secondary)')

export function MatchupTeaser({ g }: { g: Game }) {
  const sides = g.edge_cards ?? []
  if (sides.length === 0 && !g.matchups?.lede) return null
  return (
    <Card title="The matchup" tab="tendencies" more="All matchups" testid="teaser-matchup">
      {g.matchups?.lede && <p className="mb-3 mt-0 max-w-3xl text-[13px] text-ink">{g.matchups.lede}</p>}
      {sides.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {sides.map((s) => (
            <EdgeCard key={s.team} side={s} colorOf={colorFor(g)} compact />
          ))}
        </div>
      )}
      {sides.length > 0 && <p className="mb-0 mt-2 text-[11px] text-ink-3">Grey: how often teams in this spot won since 2006. Bold: when they won that battle.</p>}
    </Card>
  )
}

const TOP_FACTORS = 3

export function EdgeTeaser({ g, meta }: { g: Game; meta: Meta }) {
  if (!g.contributions.global) return null
  const rows = previewRows(g, meta, null)
    .filter((r) => r.pp != null)
    .sort((a, b) => Math.abs(b.pp!) - Math.abs(a.pp!))
    .slice(0, TOP_FACTORS)
  if (rows.length === 0) return null
  const domain = Math.max(1, ...rows.map((r) => Math.abs(r.pp ?? 0))) * 1.25
  return (
    <Card title="Who has the edge" tab="approaches" more="Every factor and approach" testid="teaser-edge">
      <p className="mb-2 mt-0 text-[13px] text-ink-2">The three parts of the game that lean furthest, priced by history.</p>
      <DivergingBars
        leftLabel={`toward ${g.away}`}
        rightLabel={`toward ${g.home}`}
        domain={domain}
        format={ptsFor}
        rowHeight={34}
        leftColor="var(--team-away)"
        rightColor="var(--team-home)"
        ariaLabel={rows.map((r) => `${r.name}: ${ptsFor(r.pp!)}`).join('; ')}
        rows={rows.map((r) => ({ key: r.id, label: <span className="truncate text-ink">{r.name}</span>, value: r.pp }))}
      />
    </Card>
  )
}

function Spark({ values }: { values: number[] }) {
  const w = 120
  const h = 28
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const pts = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * w},${h - 4 - ((v - lo) / span) * (h - 8)}`).join(' ')
  return (
    <svg width={w} height={h} aria-hidden className="shrink-0 text-ink-2">
      <polyline fill="none" stroke="currentColor" strokeWidth={1.5} points={pts} />
    </svg>
  )
}

export function LineTeaser({ g }: { g: Game }) {
  if (!hasLine(g)) return null
  const h = g.market_history
  const first = h[0]
  const last = h[h.length - 1]
  const now = spreadLabel(last.spread_home, g.home, g.away)
  const was = spreadLabel(first.spread_home, g.home, g.away)
  const moved = first.spread_home !== last.spread_home
  const total = first.total != null && last.total != null ? (first.total === last.total ? `the total ${last.total}` : `the total ${first.total} → ${last.total}`) : null
  return (
    <Card title="The line" tab="line" more="Movement and every book" testid="teaser-line">
      <div className="flex items-center gap-3 text-[13px]">
        <Spark values={h.map((p) => p.spread_home ?? 0)} />
        <span>
          {moved ? `${was} when first seen ${dayOf(first.ts)}, now ${now}` : `${now} since first seen ${dayOf(first.ts)}`}
          {total ? `; ${total}` : ''}.{' '}
          {disagrees(g.books) ? <span className="text-[var(--warning)]">The books disagree.</span> : last.n_books != null ? `${last.n_books} books.` : ''}
        </span>
      </div>
    </Card>
  )
}

export function NewsTeaser({ g }: { g: Game }) {
  const a = topAbsence(g.injuries)
  const n = g.narrative
  const note = n ? sortMatchupNotes(n.matchup_notes)[0] : null
  if (!a && !n) return null
  const firstSentence = (t: string) => (t.match(/^.*?[.!?](\s|$)/)?.[0] ?? t).trim()
  return (
    <Card title="Injuries & news" tab="news" more="Full report and sources" testid="teaser-news">
      <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px]">
        {a && (
          <li>
            <b>Key absence:</b> {a.top.player} ({a.top.team}
            {a.top.pos ? ` ${a.top.pos}` : ''}, {a.top.status.toLowerCase()}){a.count > 1 ? `, and ${a.count - 1} more` : ''}
          </li>
        )}
        {n?.consensus_narrative && <li>{firstSentence(n.consensus_narrative)}</li>}
        {note && <li>{firstSentence(note.text)}</li>}
      </ul>
    </Card>
  )
}

const TOP_GAPS = 3

export function TapeTeaser({ g, meta }: { g: Game; meta: Meta }) {
  const rows = tape(g.features, meta)
    .flatMap((t) => t.groups.flatMap((x) => x.rows))
    .filter((r) => r.band)
    .map((r) => ({ r, gap: Math.abs(r.band!.homeV - r.band!.awayV) / (r.band!.q3 - r.band!.q1) }))
    .sort((a, b) => b.gap - a.gap)
    .slice(0, TOP_GAPS)
  if (rows.length === 0) return null
  return (
    <Card title="Tale of the tape" tab="details" more="Every stat on the league band" testid="teaser-tape">
      <p className="mb-1 mt-0 text-[13px] text-ink-2">Where the two teams sit furthest apart:</p>
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
  return (
    <div className="flex flex-col gap-4" data-testid="preview-hub">
      <MatchupTeaser g={g} />
      <EdgeTeaser g={g} meta={meta} />
      <LineTeaser g={g} />
      <NewsTeaser g={g} />
      <TapeTeaser g={g} meta={meta} />
    </div>
  )
}
