/**
 * The game page's default tab before kickoff: the matchup itself, approach-free. One bar per part of
 * the game, as long as history says that edge is worth; pick an approach to outline its own reading
 * on the same rows. The bars come from the Global fit, a diagnostic, so the name never appears here.
 */
import { useState } from 'react'
import { DivergingBars, TipNote, TipRow, TipTitle } from '../../charts'
import { DataTable, Section, Segmented, td, th } from '../../components/ui'
import type { Game, Meta } from '../../data/contract'
import { pct, ptsFor, ptsToward } from '../../lib/format'
import { approachOf } from '../../lib/meta'
import { SHORT } from '../../lib/models'
import { contribOrder, lineMoveChip, previewRows } from './helpers'
import { Edges } from './Sections'

const NONE = 'none'

export function Preview({ g, meta }: { g: Game; meta: Meta }) {
  const [sel, setSel] = useState(NONE)
  if (!g.contributions.global) return <Edges g={g} meta={meta} />
  const approaches = contribOrder(g.contributions)
  const overlay = sel !== NONE && approaches.some((a) => a === sel) ? sel : null
  const rows = previewRows(g, meta, overlay)
  // sized to what's on screen: one approach's outlier (the Sharp on a big line move) mustn't flatten the matchup for the rest
  const domain = Math.max(1, ...rows.flatMap((r) => [Math.abs(r.pp ?? 0), Math.abs(r.overlay ?? 0)])) * 1.25
  const chip = overlay === 'sharp' ? lineMoveChip(g) : null
  const name = overlay ? SHORT[overlay] : null
  const side = (v: number) => (v >= 0 ? 'var(--team-home)' : 'var(--team-away)')
  return (
    <Section
      title="Who has the edge"
      help="Each bar is what that edge has been worth in past games, in points of win chance, before any approach weighs in. The label under each name says how lopsided this matchup is next to every game since 2005."
    >
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">
        The matchup before any approach weighs in: how far each part of the game pushes toward {g.away} or {g.home}, as history would price it.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div className="max-w-full overflow-x-auto">
          <Segmented
            label="Overlay an approach"
            value={overlay ?? NONE}
            onChange={setSel}
            options={[{ value: NONE, label: 'No approach' }, ...approaches.map((a) => ({ value: a as string, label: SHORT[a] }))]}
          />
        </div>
        {overlay && (
          <span className="text-[13px] text-ink-2">
            Outlined: how the {name} reads each part. {name} says {g.home} {pct(g.contributions[overlay].p_home, 1)}.
          </span>
        )}
      </div>
      {overlay && approachOf(meta, overlay)?.blurb && <p className="mb-2 max-w-3xl text-[13px] text-ink-3">{approachOf(meta, overlay)?.blurb}</p>}
      {chip && <p className="mb-2 inline-block rounded border border-line bg-surface-2 px-2 py-0.5 text-[13px]">{chip}</p>}
      <DivergingBars
        leftLabel={`toward ${g.away}`}
        rightLabel={`toward ${g.home}`}
        domain={domain}
        format={ptsFor}
        rowHeight={42}
        leftColor="var(--team-away)"
        rightColor="var(--team-home)"
        overlayName={name ?? undefined}
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
          overlay: r.overlay,
          tip: (
            <>
              <TipTitle note={r.help}>{r.name}</TipTitle>
              {r.pp != null && <TipRow color={side(r.pp)} value={ptsFor(r.pp)} label={`toward ${r.pp >= 0 ? g.home : g.away}, by history`} />}
              {r.overlay != null && <TipRow color="var(--text-primary)" value={ptsFor(r.overlay)} label={`toward ${r.overlay >= 0 ? g.home : g.away}, the ${name}`} />}
              {r.pct != null && r.edge !== 'about even' && <TipNote>Bigger than {Math.round(r.pct)}% of matchups since 2005.</TipNote>}
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
              {overlay && <th className={th}>{name}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className={td}>{r.name}</td>
                <td className={td}>{r.edge || '–'}</td>
                <td className={`${td} tabular`}>{r.pp == null ? '–' : ptsToward(r.pp, g.home, g.away)}</td>
                {overlay && <td className={`${td} tabular`}>{r.overlay == null ? '–' : ptsToward(r.overlay, g.home, g.away)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}
