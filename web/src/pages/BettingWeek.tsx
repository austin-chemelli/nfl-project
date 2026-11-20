import { useId, useMemo, useState } from 'react'
import { FinePrint } from '../components/FinePrint'
import { SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs, useSetTab, type TabDef } from '../components/Tabs'
import { Loaded, Page } from '../components/ui'
import { useBettingWeek } from '../data/api'
import type { BettingWeek } from '../data/contract'
import { setBankroll, stakeFor, useBankroll } from '../lib/bankroll'
import { summarize, useBets } from '../lib/betLog'
import { BETTING_VISIBILITY, reachable } from '../lib/bettingVisibility'
import { dollars, kickoffEt, pct } from '../lib/format'
import { weekOf } from '../lib/picks'
import { useNoindex } from '../lib/useNoindex'
import { BetLog } from './betting/BetLog'
import { HelpLine } from './betting/common'
import { WeekCard, type Draft } from './betting/WeekCard'
import { WeekRecord } from './betting/WeekRecord'
import { closingMap } from './betting/weekFacts'
import NotFound from './NotFound'

function BankrollInput() {
  const id = useId()
  const bankroll = useBankroll()
  const [text, setText] = useState(bankroll == null ? '' : String(bankroll))
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor={id} className="text-[14px] text-ink-2">Your bankroll</label>
      <span className="flex items-center gap-1 rounded border border-line bg-surface-1 px-2 py-1">
        <span aria-hidden="true" className="text-ink-3">$</span>
        <input
          id={id}
          type="number"
          min="0"
          step="any"
          inputMode="decimal"
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            const n = Number(e.target.value)
            setBankroll(e.target.value.trim() !== '' && Number.isFinite(n) && n > 0 ? n : null)
          }}
          className="w-28 bg-transparent text-[14px] outline-none"
        />
      </span>
      <span className="text-[13px] text-ink-3">Kept in this browser only.</span>
    </div>
  )
}

function Body({ w }: { w: BettingWeek }) {
  const bankroll = useBankroll()
  const bets = useBets()
  const setTab = useSetTab()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [draftKey, setDraftKey] = useState(0)
  const stake = stakeFor(bankroll, w.stake_pct)
  const looks = w.card.games.filter((g) => g.verdict === 'look').length
  const logOk = reachable(BETTING_VISIBILITY.log)
  const cardOk = reachable(BETTING_VISIBILITY.card)

  const mine = useMemo(() => bets.filter((e) => weekOf(e.game_id)?.season === w.season), [bets, w.season])
  const season = useMemo(() => summarize(mine, closingMap(w)), [mine, w])
  const settled = season.bets - season.open
  const asOf = w.card.games.reduce<string | null>((a, g) => (g.market && (a == null || g.market.as_of > a) ? g.market.as_of : a), null)

  const tabs: TabDef[] = []
  if (cardOk) {
    tabs.push({
      id: 'week',
      label: 'This week',
      content: (
        <WeekCard
          w={w}
          bankroll={bankroll}
          onLog={
            logOk
              ? (d) => {
                  setDraft(d)
                  setDraftKey((k) => k + 1)
                  setTab('log')
                }
              : undefined
          }
        />
      ),
    })
  }
  if (logOk) {
    tabs.push({
      id: 'log',
      label: 'My bets',
      content: <BetLog w={w} draft={draft} draftKey={draftKey} defaultStake={stake} onAdded={() => setDraft(null)} />,
    })
  }
  if (cardOk) tabs.push({ id: 'record', label: 'Record', content: <WeekRecord w={w} /> })

  return (
    <>
      <BankrollInput />
      <SummaryStrip label="Betting card summary">
        <Tile label="Worth a look" value={`${looks} of ${w.max_looks}`} sub="games this week" tab={cardOk ? 'week' : undefined} />
        <Tile label="Stake per bet" value={stake != null ? dollars(stake) : pct(w.stake_pct, 0)} sub={stake != null ? `${pct(w.stake_pct, 0)} of your bankroll` : 'of your bankroll'} />
        <Tile label="Week" value={`Week ${w.card.week}`} sub={`${w.season} season`} />
        <Tile
          label="Your season"
          value={season.bets === 0 ? 'No bets logged' : settled === 0 ? 'Open bets only' : `${season.profit > 0 ? '+' : ''}${dollars(season.profit, 2)}`}
          sub={season.bets === 0 ? undefined : `${season.bets} ${season.bets === 1 ? 'bet' : 'bets'}${season.open ? `, ${season.open} open` : ''}`}
          tab={logOk ? 'log' : undefined}
        />
      </SummaryStrip>
      <Tabs label="Betting card sections" tabs={tabs} />
      <FinePrint>
        <p>
          No edge shown in our history: every way of betting in it loses money, and a few hundred bets can&apos;t prove otherwise. Small samples; treat betting here as a fun test, not income.
        </p>
        <p>Prices come from our latest odds snapshot{asOf ? ` (${kickoffEt(asOf)})` : ''}; they move, so check the price in the app before you buy.</p>
        <p>Not betting advice.</p>
        <HelpLine />
      </FinePrint>
    </>
  )
}

function WeekPage() {
  const q = useBettingWeek()
  useNoindex(true)
  return (
    <Page title="Your betting card" lede="This week's games under the guide's rules, with the price each bet needs and a stake from your bankroll.">
      <Loaded q={q} what="betting card" shape="tracker">
        {(w) => <Body w={w} />}
      </Loaded>
    </Page>
  )
}

export default function BettingWeekPage() {
  return reachable(BETTING_VISIBILITY.card) || reachable(BETTING_VISIBILITY.log) ? <WeekPage /> : <NotFound />
}
