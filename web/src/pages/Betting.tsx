import { useMemo, useState } from 'react'
import { FinePrint } from '../components/FinePrint'
import { Tabs, useSetTab, type TabDef } from '../components/Tabs'
import { Loaded, Page } from '../components/ui'
import { useBettingWeek } from '../data/api'
import type { BettingWeek } from '../data/contract'
import { stakeFor, useBankroll } from '../lib/bankroll'
import { BETTING_VISIBILITY, reachable } from '../lib/bettingVisibility'
import { kickoffEt, signedPct } from '../lib/format'
import { SHORT } from '../lib/models'
import { useNoindex } from '../lib/useNoindex'
import { BetLog } from './betting/BetLog'
import { HelpLine } from './betting/common'
import { ThisWeek } from './betting/ThisWeek'
import { WeekRecord } from './betting/WeekRecord'
import type { Draft } from './betting/weekFacts'
import NotFound from './NotFound'

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
      <Tabs label="Betting sections" tabs={tabs} />
      <FinePrint>
        <p className="tabular">
          Ranked by history, not a sure edge: re-ranked each season on earlier seasons only, the top {w.max_targets} a week returned {signedPct((w.rules.ranked_walk_forward ?? w.rules.ranked)?.roi)} a bet; the stay-aways {signedPct(w.rules.avoid.roi)}. Not betting advice.
        </p>
        <HelpLine />
        <p className="text-ink-3">
          Model {SHORT[w.model] ?? w.model} {w.model_version ?? ''}. Prices from our latest odds snapshot{asOf ? ` (${kickoffEt(asOf)})` : ''}; they move.
        </p>
      </FinePrint>
    </>
  )
}

function WeekPage() {
  const q = useBettingWeek()
  useNoindex(BETTING_VISIBILITY.card !== 'public')
  return (
    <Page title="This week's bets" lede="The best bets worth a look and the ones to skip, from the Student and the market.">
      <Loaded q={q} what="betting card" shape="tracker">
        {(w) => <Body w={w} />}
      </Loaded>
    </Page>
  )
}

export default function BettingPage() {
  return reachable(BETTING_VISIBILITY.card) || reachable(BETTING_VISIBILITY.log) ? <WeekPage /> : <NotFound />
}
