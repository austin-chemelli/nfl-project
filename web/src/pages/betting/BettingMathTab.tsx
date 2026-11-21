import { Link } from 'react-router'
import { FinePrint } from '../../components/FinePrint'
import { Loaded, Section } from '../../components/ui'
import { useBettingMath } from '../../data/api'
import type { BettingMath } from '../../data/contract'
import { BETTING_VISIBILITY, listed } from '../../lib/bettingVisibility'
import { HelpLine, Lede } from './common'
import { Models } from './Models'
import { Parlays } from './Parlays'
import { Prices } from './Prices'
import { ShortAnswers } from './ShortAnswers'
import { Spreads } from './Spreads'
import { Stakes } from './Stakes'
import { Where } from './Where'

function Body({ m }: { m: BettingMath }) {
  const years = m.seasons[1] - m.seasons[0] + 1
  return (
    <div className="flex flex-col gap-8">
      <Section title="Betting math">
        <Lede>What {years} seasons of our own lines say about betting NFL games: where the cost is lowest, and why there is no edge to find.</Lede>
        {listed(BETTING_VISIBILITY.card) && (
          <p className="text-[13px]">
            <Link to="/betting">This week&apos;s bets →</Link>
          </p>
        )}
      </Section>
      <Section title="Short answers">
        <ShortAnswers m={m} />
      </Section>
      <Prices m={m} />
      <Parlays m={m} />
      <Stakes m={m} />
      <Models m={m} />
      <Spreads m={m} />
      <Where m={m} />
      <FinePrint>
        <p>
          No edge shown in {years} seasons: every way of betting in this history loses money, and a few hundred bets can&apos;t prove otherwise. Treat betting here as a fun test, not income. Figures use the {m.model} line {m.model_version}, schedule lines that are roughly closing prices, and 90% ranges; the study is <code>nfl betting study</code>. Not betting advice.
        </p>
        <HelpLine />
      </FinePrint>
    </div>
  )
}

/** The betting math as documentation: the Method page's "Betting math" tab. */
export function BettingMathTab() {
  const q = useBettingMath()
  return (
    <Loaded q={q} what="betting math" shape="tracker">
      {(m) => <Body m={m} />}
    </Loaded>
  )
}
