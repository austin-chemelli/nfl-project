import { useId, useMemo, useState } from 'react'
import { FinePrint } from '../components/FinePrint'
import { Tabs, useSetTab, type TabDef } from '../components/Tabs'
import { Loaded, Page } from '../components/ui'
import { useBettingWeek } from '../data/api'
import type { BettingWeek } from '../data/contract'
import { setBankroll, stakeFor, useBankroll } from '../lib/bankroll'
import { BETTING_VISIBILITY, reachable } from '../lib/bettingVisibility'
import { kickoffEt } from '../lib/format'
import { useNoindex } from '../lib/useNoindex'
import { BetLog } from './betting/BetLog'
import { HelpLine } from './betting/common'
import { ThisWeek } from './betting/ThisWeek'
import { WeekRecord } from './betting/WeekRecord'
import type { Draft } from './betting/weekFacts'
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
  const setTab = useSetTab()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [draftKey, setDraftKey] = useState(0)
  const stake = stakeFor(bankroll, w.stake_pct)
  const logOk = reachable(BETTING_VISIBILITY.log)
  const cardOk = reachable(BETTING_VISIBILITY.card)
  const asOf = useMemo(() => w.card.games.reduce<string | null>((a, g) => (g.market && (a == null || g.market.as_of > a) ? g.market.as_of : a), null), [w])

  const tabs: TabDef[] = []
  if (cardOk) {
    tabs.push({
      id: 'week',
      label: 'This week',
      content: (
        <ThisWeek
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
      label: 'Your bets',
      content: <BetLog w={w} draft={draft} draftKey={draftKey} defaultStake={stake} onAdded={() => setDraft(null)} />,
    })
  }
  if (cardOk) tabs.push({ id: 'record', label: 'Track record', content: <WeekRecord w={w} /> })

  return (
    <>
      <BankrollInput />
      <Tabs label="Betting sections" tabs={tabs} />
      <FinePrint>
        <p>
          The 2-to-6-point limits were chosen by looking at 2006-2025, so expect less in the future; the live record at our locks is the honest test. Small samples; a fun test, not income. Not betting advice.
        </p>
        <p>Prices come from our latest odds snapshot{asOf ? ` (${kickoffEt(asOf)})` : ''}; they move, so check the price in the app before you buy.</p>
        <HelpLine />
      </FinePrint>
    </>
  )
}

function WeekPage() {
  const q = useBettingWeek()
  useNoindex(BETTING_VISIBILITY.card !== 'public')
  return (
    <Page title="This week's bets" lede="A few games worth calling your shot on, and the ones to stay away from, from the Student, the market's prices and 20 seasons of history.">
      <Loaded q={q} what="betting card" shape="tracker">
        {(w) => <Body w={w} />}
      </Loaded>
    </Page>
  )
}

export default function BettingPage() {
  return reachable(BETTING_VISIBILITY.card) || reachable(BETTING_VISIBILITY.log) ? <WeekPage /> : <NotFound />
}
