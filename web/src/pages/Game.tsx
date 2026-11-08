import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { FinePrint } from '../components/FinePrint'
import { Condensed, SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs, type TabDef } from '../components/Tabs'
import { Card, ErrorBox, Loaded, Loading, Page } from '../components/ui'
import { useGame, useMeta, useRetro, isNotFound } from '../data/api'
import type { Game, Meta, RetroGame } from '../data/contract'
import { Injuries, ApproachesVsMarket, Tendencies, TaleOfTheTape, Why } from './game/Sections'
import { GameHeader, GameTitle, PinnedResult } from './game/Header'
import { NarrativeSection } from './game/Narrative'
import { Differ, StrongCallsOutcome } from './game/Differ'
import { TheLine, hasLine } from './game/TheLine'
import { Books } from './game/Books'
import { disagrees, hasBooks } from './game/books'
import { Preview } from './game/Preview'
import { Retro } from './game/Retro'
import { summaryTiles } from './game/summary'
import { gameStatus } from './slate/helpers'
import { matchupVars } from '../lib/teamColors'

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
    <div data-matchup style={teams ? matchupVars(teams.away, teams.home) : undefined}>
    <Page title={teams ? <GameTitle {...teams} /> : 'Game'} docTitle={q.data ? `${q.data.away} @ ${q.data.home}, Week ${q.data.week}` : undefined}>
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
        <Loaded q={meta} what="game" shape="game">
          {(m) => <Loaded q={q} what="game" shape="game">{(g) => <GameBody g={g} meta={m} />}</Loaded>}
        </Loaded>
      )}
    </Page>
    </div>
  )
}

function GameBody({ g, meta }: { g: Game; meta: Meta }) {
  const final = g.result != null
  const rq = useRetro(g.game_id, final)
  const [strip, setStrip] = useState<HTMLDivElement | null>(null)
  // wait for the retro (a final game's default tab depends on it); a 404 just means not built yet
  if (final && rq.isPending) return <Loading what="game" shape="game" />
  const retro: RetroGame | null = rq.isSuccess ? rq.data : null
  const retroError = rq.isError && !isNotFound(rq.error) ? rq.error : null
  const { status } = gameStatus(g)

  const tabs: TabDef[] = []
  if (retro || retroError)
    tabs.push({ id: 'retro', label: 'What happened', content: retro ? <TabBody><Retro r={retro} /><StrongCallsOutcome g={g} /></TabBody> : <ErrorBox error={retroError} /> })
  tabs.push(
    {
      id: 'preview',
      label: 'Preview',
      content: (
        <TabBody>
          <Preview g={g} meta={meta} />
          <FinePrint>
            <p>The bars come from a fit on past seasons, not from any approach, so they are context rather than a forecast. They add up only approximately: the effects overlap.</p>
            <p>Probabilities are the models' estimates, not advice.</p>
          </FinePrint>
        </TabBody>
      ),
    },
  )
  // the line waits for data: two snapshots for a path, three books for the book-by-book (Austin, 2026-11-07)
  if (hasLine(g) || hasBooks(g))
    tabs.push({
      id: 'line',
      label: (
        <>
          The line
          {disagrees(g.books) && (
            <>
              <span aria-hidden className="ml-1.5 inline-block h-1.5 w-1.5 -translate-y-[2px] rounded-full bg-[var(--warning)]" />
              <span className="sr-only">: books disagree</span>
            </>
          )}
        </>
      ),
      content: (
        <TabBody>
          <TheLine g={g} />
          <Books g={g} />
          <FinePrint>
            {hasLine(g) && <p>How the line moved: each point is the median across sportsbooks at one of our snapshots before kickoff, with at least three books quoting it. "First seen" is our first snapshot of the game, not when books opened it; our snapshots start 2026-10-26. The events are what our data shows changed between two snapshots (the depth chart's quarterback, a starter's status on the injury report, timed when we pulled it, a result, the lock), listed beside the move, not as its cause.</p>}
            <p>What each sportsbook says: the US books our odds feed lists, at our latest snapshot before kickoff. They're flagged as disagreeing when they're 1.5 points or more apart on the spread or the total, or when the spread sits on both sides of 3, 7 or pick'em (3 and 7 are the most common winning margins, so a half point across one matters more than one anywhere else). The price beside a spread is what that side pays: a book can hold the same number and charge more for it. Not betting advice.</p>
          </FinePrint>
        </TabBody>
      ),
    })
  tabs.push(
    {
      id: 'approaches',
      label: 'Approaches',
      content: (
        <TabBody>
          <Differ g={g} meta={meta} />
          <ApproachesVsMarket g={g} meta={meta} />
          <Why g={g} meta={meta} />
          <FinePrint>
            <p>{STATUS_TEXT[status] ?? status}</p>
            <p>Probabilities are the models' estimates, not advice. The market is the reference every approach is compared with, never an input.</p>
            <p>The pieces in "why they lean" add up only approximately to the total: the effects overlap and the final probability is also calibrated.</p>
          </FinePrint>
        </TabBody>
      ),
    },
    {
      id: 'tendencies',
      label: 'Tendencies',
      content: (
        <TabBody>
          <Tendencies g={g} meta={meta} />
          <FinePrint>
            <p>Tendencies are season-to-date rates, shrunk toward the league average when plays are few. Each chart has its own scale.</p>
          </FinePrint>
        </TabBody>
      ),
    },
    {
      id: 'details',
      label: 'Details',
      content: (
        <TabBody>
          <TaleOfTheTape g={g} meta={meta} />
          <FinePrint>
            <p>The typical range runs from the league's 10th to its 90th percentile team, as of the latest data, so an older game's values sit on today's league.</p>
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

  const tiles = summaryTiles(g, meta, retro)
  return (
    <>
      {final && (
        <Condensed watch={strip}>
          <PinnedResult g={g} verdict={tiles.find((t) => t.id === 'result')?.value} ot={retro?.wp_series?.ot ?? false} />
        </Condensed>
      )}
      <GameHeader g={g} />
      <SummaryStrip ref={setStrip} label="Game summary">
        {tiles.map((t) => (
          <Tile key={t.id} label={t.label} value={t.value} sub={t.sub} tab={tabs.some((x) => x.id === t.tab) ? t.tab : undefined} modelId={t.modelId} accent={t.team === g.home ? 'var(--team-home)' : t.team === g.away ? 'var(--team-away)' : undefined} />
        ))}
      </SummaryStrip>
      <Tabs label="Game sections" tabs={tabs} default={retro ? 'retro' : 'preview'} />
      <p className="text-[12px] text-ink-3">Fan-made, not affiliated with the NFL. Not betting advice.</p>
    </>
  )
}

function TabBody({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-8">{children}</div>
}
