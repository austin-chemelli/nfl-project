/**
 * The game page's default tab before kickoff: the matchup itself, approach-free. One bar per part of
 * the game, as long as history says that edge is worth, then the live-only parts history can't price
 * (Market behavior, Buzz) as their raw readings. How each approach reads the same parts is on the
 * Approaches tab. The bars come from the Global fit, a diagnostic, so the name never appears here.
 */
import { DivergingBars, TipNote, TipRow, TipTitle } from '../../charts'
import { Help } from '../../components/Help'
import { DataTable, Section, TableScroll, td, th } from '../../components/ui'
import type { Game, Meta } from '../../data/contract'
import { ptsFor, ptsToward } from '../../lib/format'
import { edgePct } from '../../lib/meta'
import { liveOnlyGroups, liveReady, previewRows, type LiveGroup } from './helpers'
import { Edges } from './Sections'

export function Preview({ g, meta }: { g: Game; meta: Meta }) {
  if (!g.contributions.global) return <Edges g={g} meta={meta} />
  const rows = previewRows(g, meta, null)
  const live = liveOnlyGroups(g, meta)
  const domain = Math.max(1, ...rows.map((r) => Math.abs(r.pp ?? 0))) * 1.25
  const side = (v: number) => (v >= 0 ? 'var(--team-home)' : 'var(--team-away)')
  return (
    <Section
      title="Who has the edge"
      help="Each bar is what that edge has been worth in past games, in points of win chance, before any approach weighs in. The label under each name says how lopsided this matchup is next to every game since 2005."
    >
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">
        The matchup before any approach weighs in: how far each part of the game pushes toward {g.away} or {g.home}, as history would price it. Pts are percentage points of win chance. How each approach reads the same parts is on the Approaches tab.
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
      {liveReady(live) && <LiveOnly g={g} groups={live} />}
    </Section>
  )
}

/** Market behavior and Buzz: no history to price them, so the readings themselves, per team or for the game. */
function LiveOnly({ g, groups }: { g: Game; groups: LiveGroup[] }) {
  return (
    <div className="mt-5" data-testid="live-only">
      <h3 className="mb-1 text-[15px] font-semibold">Live only: no history to price these</h3>
      <p className="mb-2 max-w-3xl text-[13px] text-ink-2">
        These readings exist only for live games, so past seasons can't say what they are worth and there is no bar. Some approaches weigh them anyway; the Approaches tab shows how much.
      </p>
      <TableScroll>
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Reading</th>
              <th className={th}>{g.away}</th>
              <th className={th}>{g.home}</th>
            </tr>
          </thead>
          <tbody>
            {groups.flatMap((grp) => [
              <tr key={grp.id}>
                <td colSpan={3} className={`${td} pt-3 text-[12px] font-medium uppercase tracking-wide text-ink-3`}>
                  <Help text={grp.help}>{grp.name}</Help>
                </td>
              </tr>,
              ...grp.readings.map((r) => (
                <tr key={r.feature}>
                  <td className={td}><Help text={r.help}>{r.label}</Help></td>
                  {r.game != null || (r.away == null && r.home == null) ? (
                    <td colSpan={2} className={`${td} tabular`}>{r.game ?? 'no reading yet'}</td>
                  ) : (
                    <>
                      <td className={`${td} tabular`}>{r.away ?? '–'}</td>
                      <td className={`${td} tabular`}>{r.home ?? '–'}</td>
                    </>
                  )}
                </tr>
              )),
            ])}
          </tbody>
        </table>
      </TableScroll>
    </div>
  )
}
