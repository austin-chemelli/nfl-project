/**
 * The game page's default tab before kickoff: the matchup itself, approach-free. One bar per part of
 * the game, as long as history says that edge is worth, then the live-only parts history can't price
 * (Market behavior, Buzz) as their raw readings. How each approach reads the same parts is on the
 * Approaches tab. The bars come from the Global fit, a diagnostic, so the name never appears here.
 */
import { Help } from '../../components/Help'
import { UpsetPaths } from '../../components/UpsetPaths'
import { useSetTab } from '../../components/Tabs'
import { DivergingBars, TipNote, TipRow, TipTitle } from '../../charts'
import { DataTable, Section, td, th } from '../../components/ui'
import type { Game, Meta } from '../../data/contract'
import { ptsFor, ptsToward } from '../../lib/format'
import { edgePct } from '../../lib/meta'
import { liveBars, liveOnlyGroups, liveReady, previewRows, type LiveBar } from './helpers'
import { Edges } from './Sections'

export function Preview({ g, meta }: { g: Game; meta: Meta }) {
  const setTab = useSetTab() // before the early return: hooks keep their order
  if (!g.contributions.global) return <Edges g={g} meta={meta} />
  const rows = previewRows(g, meta, null)
  const live = liveOnlyGroups(g, meta)
  const bars = liveBars(g, meta).filter((b) => b.lean != null) // a reading the week hasn't produced isn't a row
  const domain = Math.max(1, ...rows.map((r) => Math.abs(r.pp ?? 0))) * 1.25
  const side = (v: number) => (v >= 0 ? 'var(--team-home)' : 'var(--team-away)')
  return (
    <Section
      title="Who has the edge"
      help="Each bar is what that edge was worth in past games, in points (percentage points of win chance). The label under each name compares this matchup with every game since 2005."
    >
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">
        How much each part of the game favors {g.away} or {g.home}, priced by history.{' '}
        <button type="button" onClick={() => setTab('approaches')} className="cursor-pointer border-0 bg-transparent p-0 text-[13px] text-accent hover:underline">By approach →</button>
      </p>
      <DivergingBars
        leftLabel={`toward ${g.away}`}
        rightLabel={`toward ${g.home}`}
        domain={domain}
        format={ptsFor}
        rowHeight={42}
        leftColor="var(--team-away)"
        rightColor="var(--team-home)"
        ariaLabel={rows.map((r) => `${r.name}: ${r.pp == null ? 'no bar' : ptsToward(r.pp, g.home, g.away)}${r.edge ? `, ${r.edge}` : ''}`).join('; ')}
        rows={rows.map((r) => ({
          key: r.id,
          label: (
            <span className="flex min-w-0 flex-col leading-tight">
              <span className="truncate text-ink">{r.name}</span>
              {r.edge && <span className="truncate text-[11px] text-ink-3">{r.edge}</span>}
            </span>
          ),
          value: r.pp,
          tip: (
            <>
              <TipTitle note={r.help}>{r.name}</TipTitle>
              {r.pp != null && <TipRow color={side(r.pp)} value={ptsFor(r.pp)} label={`toward ${r.pp >= 0 ? g.home : g.away}, by history`} />}
              {r.pct != null && r.edge !== 'about even' && <TipNote>Bigger than {edgePct(r.pct)}% of matchups since 2005.</TipNote>}
            </>
          ),
        }))}
      />
      <DataTable>
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Part of the game</th>
              <th className={th}>Edge</th>
              <th className={th}>Worth</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className={td}>{r.name}</td>
                <td className={td}>{r.edge || '–'}</td>
                <td className={`${td} tabular`}>{r.pp == null ? '–' : ptsToward(r.pp, g.home, g.away)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
      {liveReady(live) && <LiveBars bars={bars} />}
      <UpsetPaths paths={g.paths} outcome={g.paths_outcome} />
    </Section>
  )
}

/** Market behavior and Buzz (Austin, 2026-11-07): this week's readings as bars beside the ones
 * history prices, set apart under a "Live" heading. History can't price them, so each bar is on its
 * own scale and labelled in its own units; lighter team colors say they aren't the same measure. */
function LiveBars({ bars }: { bars: LiveBar[] }) {
  const light = (c: string) => `color-mix(in srgb, ${c} 55%, transparent)`
  return (
    <div className="mt-6 border-t border-dashed border-line pt-4" data-testid="live-only">
      <div className="flex items-baseline gap-2">
        <span className="rounded border border-[var(--text-muted)] px-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-2">Live</span>
        <h3 className="m-0 text-[15px] font-semibold">
          <Help text="Readings from this week's lines and news. Read which way a bar leans, not its length next to the bars above.">This week only</Help>
        </h3>
      </div>
      <p className="mb-2 mt-1 max-w-3xl text-[13px] text-ink-2">No history to price these, so each bar has its own scale.</p>
      <DivergingBars
        domain={1.6} // the longest bar stops short of the edge, so its label always fits
        format={() => ''}
        rowHeight={42}
        leftColor={light('var(--team-away)')}
        rightColor={light('var(--team-home)')}
        ariaLabel={bars.map((b) => `${b.label}: ${b.text ?? 'no reading yet'}${b.toward ? `, toward ${b.toward}` : ''}`).join('; ')}
        rows={bars.map((b) => ({
          key: b.feature,
          label: (
            <span className="flex min-w-0 flex-col leading-tight">
              <span className="truncate text-ink">{b.label}</span>
              <span className="truncate text-[11px] text-ink-3">{b.group}</span>
            </span>
          ),
          value: b.lean,
          text: b.text ?? undefined,
          tip: (
            <>
              <TipTitle note={b.help}>{b.label}</TipTitle>
              <TipNote>{b.text == null ? 'No reading yet.' : `${b.both ?? b.text}${b.toward ? `: leans toward ${b.toward}` : ': no lean'}.`}</TipNote>
            </>
          ),
        }))}
      />
      <DataTable>
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Live reading</th>
              <th className={th}>Reading</th>
              <th className={th}>Leans toward</th>
            </tr>
          </thead>
          <tbody>
            {bars.map((b) => (
              <tr key={b.feature}>
                <td className={td}>{b.label}</td>
                <td className={`${td} tabular`}>{b.both ?? b.text ?? 'no reading yet'}</td>
                <td className={td}>{b.toward ?? '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </div>
  )
}
