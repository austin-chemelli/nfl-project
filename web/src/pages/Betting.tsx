import type { ReactNode } from 'react'
import { FinePrint } from '../components/FinePrint'
import { SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs } from '../components/Tabs'
import { Loaded, Page } from '../components/ui'
import { Link } from 'react-router'
import { useBettingMath } from '../data/api'
import type { BettingMath } from '../data/contract'
import { pct, signedPct } from '../lib/format'
import { BETTING_VISIBILITY, listed, reachable } from '../lib/bettingVisibility'
import { useNoindex } from '../lib/useNoindex'
import { HelpLine } from './betting/common'
import { chance } from './betting/facts'
import { Models } from './betting/Models'
import { Parlays } from './betting/Parlays'
import { Prices } from './betting/Prices'
import { ShortAnswers } from './betting/ShortAnswers'
import { Spreads } from './betting/Spreads'
import { Stakes } from './betting/Stakes'
import { Where } from './betting/Where'
import NotFound from './NotFound'

function TabBody({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-8">{children}</div>
}

function Tiles({ m }: { m: BettingMath }) {
  const heavy = m.bands.find((b) => b.band === 'heavy_fav')
  const coin = m.bands.find((b) => b.band === 'coin')
  const single = m.parlays.find((p) => p.legs === 1)
  const four = m.parlays.find((p) => p.legs === 4)
  const at6 = (id: string) => m.staking.find((s) => s.strategy === id && s.bets_per_week === 6)
  return (
    <SummaryStrip label="Betting math summary">
      <Tile label="Singles or parlays?" value={signedPct(single?.roi)} sub={`4 legs: ${signedPct(four?.roi)}`} tab="short" />
      <Tile label="Heavy favorites" value={signedPct(heavy?.roi)} sub={`win ${pct(heavy?.win_rate)}, the least costly price`} tab="prices" />
      <Tile label="Coin flips" value={signedPct(coin?.roi)} sub="you pay the cut, nothing else" tab="prices" />
      <Tile label="Stake per bet" value="1%" sub={`lost half the bankroll in ${chance(at6('flat_1')?.p_lose_half)} of seasons; 5%: ${chance(at6('flat_5')?.p_lose_half)}`} tab="stakes" />
    </SummaryStrip>
  )
}

function Body({ m }: { m: BettingMath }) {
  const years = m.seasons[1] - m.seasons[0] + 1
  return (
    <>
      <Tiles m={m} />
      <Tabs
        label="Betting math sections"
        default="short"
        tabs={[
          { id: 'short', label: 'Short answers', content: <TabBody><ShortAnswers m={m} /></TabBody> },
          { id: 'prices', label: 'Prices', content: <TabBody><Prices m={m} /></TabBody> },
          { id: 'parlays', label: 'Parlays', content: <TabBody><Parlays m={m} /></TabBody> },
          { id: 'stakes', label: 'How much to stake', content: <TabBody><Stakes m={m} /></TabBody> },
          { id: 'models', label: 'Our models', content: <TabBody><Models m={m} /></TabBody> },
          { id: 'spreads', label: 'Spreads and totals', content: <TabBody><Spreads m={m} /></TabBody> },
          { id: 'where', label: 'Where and how', content: <TabBody><Where m={m} /></TabBody> },
        ]}
      />
      <FinePrint>
        <p>
          No edge shown in {years} seasons: every way of betting in this history loses money, and a few hundred bets can&apos;t prove otherwise. Treat betting here as a fun test, not income. Figures use the {m.model} line {m.model_version}, schedule lines that are roughly closing prices, and 90% ranges; the study is <code>nfl betting study</code>. Not betting advice.
        </p>
        <HelpLine />
      </FinePrint>
    </>
  )
}

function MathPage() {
  const q = useBettingMath()
  useNoindex(BETTING_VISIBILITY.math !== 'public')
  return (
    <Page
      title="Betting math"
      lede={
        q.data
          ? `What ${q.data.seasons[1] - q.data.seasons[0] + 1} seasons of our own lines say about betting NFL games: where the cost is lowest, and why there is no edge to find.`
          : 'What our own lines say about betting NFL games: where the cost is lowest, and why there is no edge to find.'
      }
    >
      {listed(BETTING_VISIBILITY.card) && (
        <p className="-mt-3 text-[13px]">
          <Link to="/betting/week">Your weekly card →</Link>
        </p>
      )}
      <Loaded q={q} what="betting math" shape="tracker">
        {(m) => <Body m={m} />}
      </Loaded>
    </Page>
  )
}

export default function BettingPage() {
  return reachable(BETTING_VISIBILITY.math) ? <MathPage /> : <NotFound />
}
