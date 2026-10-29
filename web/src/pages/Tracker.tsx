import { Page, Loaded, Section } from '../components/ui'
import { useMeta, useTracker } from '../data/api'
import { CurrentSeason } from './tracker/CurrentSeason'
import { Backtest } from './tracker/Backtest'
import { Calibration } from './tracker/Calibration'
import { Divergence } from './tracker/Divergence'
import { Ledger } from './tracker/Ledger'
import { PersonaHistory } from './tracker/PersonaHistory'
import { SeasonTable } from './tracker/SeasonTable'

export default function TrackerPage() {
  const tracker = useTracker()
  const meta = useMeta()
  return (
    <Page
      title="Season tracker"
      lede="Forecast quality comes first (log loss: lower is better; 0.693 is a coin flip), paper bets second. About 180 live games a season cannot rank models, and in the 2005 to 2025 backtest nothing beats the market. Treat everything here as a measurement, not a verdict."
    >
      <Loaded q={tracker} what="tracker">
        {(t) => (
          <Loaded q={meta} what="tracker">
            {(m) => (
              <>
                <CurrentSeason t={t} meta={m} />
                <Backtest t={t} meta={m} />
                <Calibration t={t} meta={m} />
                <Divergence t={t} meta={m} />
                <Ledger t={t} />
                <PersonaHistory meta={m} />
                <Section title="Log loss by season" help="Seasons are noisy (about 285 games each); the gaps between lines matter more than the wiggle.">
                  <SeasonTable t={t} />
                </Section>
              </>
            )}
          </Loaded>
        )}
      </Loaded>
    </Page>
  )
}
