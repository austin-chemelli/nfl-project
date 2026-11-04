import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { FinePrint } from '../components/FinePrint'
import { SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs, type TabDef } from '../components/Tabs'
import { Card, ErrorBox, Loaded, Loading, Page } from '../components/ui'
import { useGame, useMeta, useRetro, isNotFound } from '../data/api'
import type { Game, Meta, RetroGame } from '../data/contract'
import { Edges, Injuries, ApproachesVsMarket, Tendencies, TaleOfTheTape, Why } from './game/Sections'
import { GameHeader, GameTitle } from './game/Header'
import { NarrativeSection } from './game/Narrative'
import { Retro } from './game/Retro'
import { summaryTiles } from './game/summary'
import { gameStatus } from './slate/helpers'

const STATUS_TEXT: Record<string, string> = {
  preview: 'Preview: scored now, not yet a lock.',
  locked: 'Locked: recorded before kickoff.',
  backfill: 'Backfill: finished game scored after the fact by frozen models.',
  pregame: 'Not locked: no lock was recorded before kickoff, so this is what the models said an hour before kickoff, using only data known then. Not part of the live record.',
  none: 'No approach forecasts for this game yet: it has not been locked or scored.',
}

/** "2026_08_CAR_GB" -> CAR @ GB so the title shows before the data arrives. */
function teamsOf(id: string | undefined): { away: string; home: string } | null {
  const m = id?.match(/^\d{4}_\d{2}_([A-Z]+)_([A-Z]+)$/)
  return m ? { away: m[1], home: m[2] } : null
}

export default function GamePage() {
  const { id } = useParams()
  const q = useGame(id)
  const meta = useMeta()
  const missing = q.isError && isNotFound(q.error)
  const teams = teamsOf(id)
  return (
    <Page title={teams ? <GameTitle {...teams} /> : 'Game'}>
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
  const final = g.result != null
  const rq = useRetro(g.game_id, final)
  // wait for the retro (a final game's default tab depends on it); a 404 just means not built yet
  if (final && rq.isPending) return <Loading what="game" />
  const retro: RetroGame | null = rq.isSuccess ? rq.data : null
  const retroError = rq.isError && !isNotFound(rq.error) ? rq.error : null
  const { status } = gameStatus(g)

  const tabs: TabDef[] = []
  if (retro || retroError)
    tabs.push({ id: 'retro', label: 'What happened', content: retro ? <Retro r={retro} /> : <ErrorBox error={retroError} /> })
  tabs.push(
    {
      id: 'forecast',
      label: final ? 'Pregame forecast' : 'Forecast',
      content: (
        <TabBody>
          <ApproachesVsMarket g={g} meta={meta} />
          <Why g={g} meta={meta} />
          <Edges g={g} meta={meta} />
          <FinePrint>
            <p>{STATUS_TEXT[status] ?? status}</p>
            <p>Probabilities are the models' estimates, not advice. The market is the reference every approach is compared with, never an input.</p>
            <p>The pieces in "why they lean" add up only approximately to the total: the effects overlap and the final probability is also calibrated.</p>
          </FinePrint>
        </TabBody>
      ),
    },
    {
      id: 'matchup',
      label: 'Matchup',
      content: (
        <TabBody>
          <TaleOfTheTape g={g} meta={meta} />
          <Tendencies g={g} meta={meta} />
          <FinePrint>
            <p>Tendencies are season-to-date rates, shrunk toward the league average when plays are few. Each chart has its own scale.</p>
            <p>Values that describe the game as a whole (like the market line) show the same number for both teams.</p>
          </FinePrint>
        </TabBody>
      ),
    },
    {
      id: 'news',
      label: 'Injuries & news',
      content: (
        <TabBody>
          <Injuries g={g} />
          <NarrativeSection g={g} />
        </TabBody>
      ),
    },
  )

  return (
    <>
      <GameHeader g={g} />
      <SummaryStrip label="Game summary">
        {summaryTiles(g, meta, retro).map((t) => (
          <Tile key={t.id} label={t.label} value={t.value} sub={t.sub} tab={tabs.some((x) => x.id === t.tab) ? t.tab : undefined} modelId={t.modelId} />
        ))}
      </SummaryStrip>
      <Tabs label="Game sections" tabs={tabs} default={retro ? 'retro' : 'forecast'} />
      <p className="text-[12px] text-ink-3">Fan-made, not affiliated with the NFL. Not betting advice.</p>
    </>
  )
}

function TabBody({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-8">{children}</div>
}
