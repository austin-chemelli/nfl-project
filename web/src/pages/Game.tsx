import { Link, useParams } from 'react-router'
import { Card, ErrorBox, Loaded, Page, StatusBadge } from '../components/ui'
import { useGame, useMeta, isNotFound } from '../data/api'
import type { Game, Meta } from '../data/contract'
import { kickoffEt, pct, spreadLabel } from '../lib/format'
import { Edges, Injuries, ApproachesVsMarket, Tendencies, TaleOfTheTape, Why } from './game/Sections'
import { NarrativeSection } from './game/Narrative'
import { gameStatus } from './slate/helpers'

const STATUS_TEXT: Record<string, string> = {
  preview: 'Preview: scored now, not yet a lock.',
  locked: 'Locked: recorded before kickoff.',
  backfill: 'Backfill: finished game scored after the fact by frozen models.',
}

/** "2026_08_CAR_GB" -> "CAR @ GB" so the title shows before the data arrives. */
function titleFor(id: string | undefined): string {
  const m = id?.match(/^\d{4}_\d{2}_([A-Z]+)_([A-Z]+)$/)
  return m ? `${m[1]} @ ${m[2]}` : 'Game'
}

export default function GamePage() {
  const { id } = useParams()
  const q = useGame(id)
  const meta = useMeta()
  const missing = q.isError && isNotFound(q.error)
  return (
    <Page title={titleFor(id)}>
      {missing ? (
        <Card>
          <div className="font-medium">No detail file for this game yet.</div>
          <p className="mt-1 text-ink-2">
            Game pages appear once the week's slate is published. <Link to="/" className="text-accent hover:underline">Back to the current slate</Link>.
          </p>
        </Card>
      ) : q.isError ? (
        <ErrorBox error={q.error} />
      ) : (
        <Loaded q={meta} what="site info">
          {(m) => <Loaded q={q} what="game">{(g) => <GameBody g={g} meta={m} />}</Loaded>}
        </Loaded>
      )}
    </Page>
  )
}

function GameBody({ g, meta }: { g: Game; meta: Meta }) {
  const mk = g.market
  const { status } = gameStatus(g)
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2 text-ink-2">
          <span>{kickoffEt(g.kickoff_utc)}</span>
          <span>·</span>
          <span>{g.stadium ?? 'stadium n/a'}{g.roof ? ` (${g.roof})` : ''}{g.neutral_site ? ' · neutral site' : ''}</span>
          <StatusBadge status={status} />
        </div>
        <div><b>QBs:</b> {g.away} {g.away_qb ?? 'n/a'}, {g.home} {g.home_qb ?? 'n/a'}</div>
        <div>
          <b>Market:</b> {spreadLabel(mk?.spread_home, g.home, g.away)}, total {mk?.total ?? '–'}, {g.home} win {pct(mk?.p_home)}
        </div>
        {g.result && (
          <div className="rounded-md border border-[var(--good)] px-3 py-2 font-medium">
            Final: {g.away} {g.result.away_score}, {g.home} {g.result.home_score}
          </div>
        )}
        <div className="text-[13px] text-ink-3">{STATUS_TEXT[status] ?? status}</div>
      </div>
      <ApproachesVsMarket g={g} meta={meta} />
      <Why g={g} meta={meta} />
      <Edges g={g} meta={meta} />
      <TaleOfTheTape g={g} meta={meta} />
      <Tendencies g={g} meta={meta} />
      <Injuries g={g} />
      <NarrativeSection g={g} />
      <p className="text-[13px] text-ink-3">Probabilities are the models' estimates, not advice. Fan-made, not affiliated with the NFL.</p>
    </>
  )
}
