import type { ReactNode } from 'react'
import { FinePrint } from '../components/FinePrint'
import { SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs } from '../components/Tabs'
import { Page, Loaded, Section } from '../components/ui'
import { useMeta, useTracker } from '../data/api'
import { CurrentSeason } from './tracker/CurrentSeason'
import { Backtest } from './tracker/Backtest'
import { Calibration } from './tracker/Calibration'
import { Divergence } from './tracker/Divergence'
import { Ledger } from './tracker/Ledger'
import { PersonaHistory } from './tracker/PersonaHistory'
import { SeasonTable } from './tracker/SeasonTable'
import { summaryTiles } from './tracker/summary'

function TabBody({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-8">{children}</div>
}

export default function TrackerPage() {
  const tracker = useTracker()
  const meta = useMeta()
  return (
    <Page title="Season tracker" lede="How the forecasts are scoring against the market (log loss: lower is better; 0.693 is a coin flip).">
      <Loaded q={tracker} what="tracker">
        {(t) => (
          <Loaded q={meta} what="tracker">
            {(m) => (
              <>
                <SummaryStrip label="Tracker summary">
                  {summaryTiles(t).map((x) => (
                    <Tile key={x.id} label={x.label} value={x.value} sub={x.sub} tab={x.tab} modelId={x.modelId} />
                  ))}
                </SummaryStrip>
                <Tabs
                  label="Tracker sections"
                  default="season"
                  tabs={[
                    {
                      id: 'season',
                      label: 'This season',
                      content: (
                        <TabBody>
                          <CurrentSeason t={t} meta={m} />
                          <FinePrint>
                            <p>About 180 live games a season cannot rank models, and in the 2005 to 2025 backtest nothing beats the market. Treat everything here as a measurement, not a verdict.</p>
                            <p>{t.current_season.some((r) => r.live) ? 'Before the dashed vertical line, weeks are backfill: models frozen before the season, scored after the fact. A week with any live lock counts from there, with diamonds marking it.' : 'Every week so far is backfill: models frozen before the season, scored after the fact. A dashed vertical line will mark the first week with a graded lock.'} The gray band is roughly the 90% range of a gap at this sample size, so a line inside it can't be told from the market. A handful of 16-game weeks is very noisy, so lines crossing early means little.</p>
                            <p>The chart is a running average since week 1, so early weeks swing and later ones settle. &quot;Show the numbers&quot; lists the raw log loss for every line, the market included.</p>
                          </FinePrint>
                        </TabBody>
                      ),
                    },
                    {
                      id: 'backtest',
                      label: 'Backtest',
                      content: (
                        <TabBody>
                          <Backtest t={t} meta={m} />
                          <PersonaHistory meta={m} />
                          <Section title="Log loss by season" help="Seasons are noisy (about 285 games each); the gaps between lines matter more than the wiggle.">
                            <SeasonTable t={t} />
                          </Section>
                          <Divergence t={t} meta={m} />
                          <FinePrint>
                            <p>Whiskers are a 90% range from resampling whole seasons. The zero line is the market; an approach only beats it if its whole whisker sits left of the line.</p>
                            <p>For each group of evidence: what the persona believes, the public line (the persona after light fitting and calibration, which is what is scored above), and what history alone would choose. Bars are shares of the 100-point attention budget; a negative bar means history says the group points the other way.</p>
                            <p>The season table shows mean log loss per season (0.693 is a coin flip); read each cell against the Market column.</p>
                            <p>Disagreement is in points of win probability. If an approach saw something the market missed, its side would win more often than the market expected, so compare those two columns. An approach can lean the right way and still lose on log loss by moving too far: the columns test the direction, log loss tests the size.</p>
                          </FinePrint>
                        </TabBody>
                      ),
                    },
                    {
                      id: 'calibration',
                      label: 'Calibration',
                      content: (
                        <TabBody>
                          <Calibration t={t} meta={m} />
                          <FinePrint>
                            <p>The dotted diagonal is perfect calibration. Each game counts toward the team the approach favored (so a 25% home team is a 75% away team). The highest bins hold few games, so their wobble is mostly noise.</p>
                          </FinePrint>
                        </TabBody>
                      ),
                    },
                    {
                      id: 'bets',
                      label: 'Paper bets',
                      content: (
                        <TabBody>
                          <Ledger t={t} meta={m} />
                          <FinePrint>
                            <p><strong className="text-ink">Not betting advice; small samples.</strong> Season profit and loss is mostly noise; closing-line value (CLV, whether the price you got beat the final price) is the better edge signal.</p>
                            <p>Backfill bets are priced at nflverse&apos;s closing-ish line, so their ROI is a harsh lower bound and their CLV is undefined. Backfill rows cover every graded season in the backtest, not just this one; live rows appear after the first graded locks. Losing a few percent into the market&apos;s price is what a model that trails the market looks like.</p>
                            <p>No edge means the market&apos;s own win chance at the price paid, or a coin flip on a spread; what is left is the bookmaker&apos;s cut. In our price data the moneyline cut is under 3% through 2022 and about 4.3% from 2023, so older seasons are a little easier on every line. The 90% range is 1.645 standard errors of the profit per bet.</p>
                          </FinePrint>
                        </TabBody>
                      ),
                    },
                  ]}
                />
              </>
            )}
          </Loaded>
        )}
      </Loaded>
    </Page>
  )
}
