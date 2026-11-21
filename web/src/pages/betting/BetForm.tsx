import { useState, type FormEvent } from 'react'
import { addBet, americanFromCents, newBetId, nowIso, validPrice, VENUES, type BetEntry, type Market, type Side } from '../../lib/betLog'
import { american } from '../../lib/format'
import type { Draft, GameOption } from './weekFacts'

const field = 'w-full rounded border border-line bg-surface-1 px-2 py-1 text-[14px]'
const num = (s: string) => (s.trim() === '' ? NaN : Number(s.trim().replace('−', '-')))

/** Add a bet to the private log. `draft` prefills it (the card's "Log this bet"). */
export function BetForm({ games, draft, defaultStake, onAdded }: { games: GameOption[]; draft: Draft | null; defaultStake: number | null; onAdded: () => void }) {
  const [gameId, setGameId] = useState(draft?.game_id ?? games[0]?.game_id ?? '')
  const [market, setMarket] = useState<Market>('ml')
  const [side, setSide] = useState<Side>(draft?.side ?? 'home')
  const [line, setLine] = useState('')
  const [mode, setMode] = useState<'american' | 'cents'>('american')
  const [priceText, setPriceText] = useState(draft ? String(draft.price) : '')
  const [stake, setStake] = useState((draft?.stake ?? defaultStake) != null ? String(draft?.stake ?? defaultStake) : '')
  const [fee, setFee] = useState('')
  const [venue, setVenue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const game = games.find((g) => g.game_id === gameId)
  const total = market === 'total'
  // a side that doesn't fit the market falls back to the first one that does
  const sideNow: Side = total ? (side === 'over' || side === 'under' ? side : 'under') : side === 'home' || side === 'away' ? side : 'home'
  const priceNum = num(priceText)
  const asAmerican = mode === 'cents' ? americanFromCents(priceNum) : priceNum

  function submit(ev: FormEvent) {
    ev.preventDefault()
    const stakeN = num(stake)
    const feeN = fee.trim() === '' ? 0 : num(fee)
    const lineN = num(line)
    if (!game) return setError('Pick a game.')
    if (market !== 'ml' && !Number.isFinite(lineN)) return setError(total ? 'Enter the total (for example 44.5).' : 'Enter the spread point for your side (for example −3.5).')
    if (asAmerican == null || !validPrice(asAmerican)) return setError(mode === 'cents' ? 'Enter a price from 1 to 99 cents.' : 'Enter an American price of −100 or lower, or +100 or higher.')
    if (!(stakeN > 0)) return setError('Enter a stake above zero.')
    if (!(feeN >= 0)) return setError('The fee can’t be negative.')
    const e: BetEntry = {
      id: newBetId(),
      game_id: game.game_id,
      market,
      side: sideNow,
      line: market === 'ml' ? null : lineN,
      price: asAmerican,
      stake: stakeN,
      fee: feeN,
      venue: venue.trim(),
      placed_at: nowIso(),
    }
    addBet(e)
    setError(null)
    setLine('')
    setPriceText('')
    setFee('')
    onAdded()
  }

  return (
    <form onSubmit={submit} aria-label="Log a bet" className="grid gap-3 rounded-lg border border-line bg-surface-1 p-4 sm:grid-cols-2 lg:grid-cols-3">
      <label className="flex flex-col gap-1 text-[13px] text-ink-2 sm:col-span-2 lg:col-span-1">
        Game
        <select className={field} value={gameId} onChange={(e) => setGameId(e.target.value)}>
          {games.map((g) => (
            <option key={g.game_id} value={g.game_id}>{g.label}</option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[13px] text-ink-2">
        Market
        <select className={field} value={market} onChange={(e) => setMarket(e.target.value as Market)}>
          <option value="ml">Moneyline</option>
          <option value="spread">Spread</option>
          <option value="total">Total</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[13px] text-ink-2">
        Side
        <select className={field} value={sideNow} onChange={(e) => setSide(e.target.value as Side)}>
          {total ? (
            <>
              <option value="over">Over</option>
              <option value="under">Under</option>
            </>
          ) : (
            <>
              <option value="home">{game?.home ?? 'Home'}</option>
              <option value="away">{game?.away ?? 'Away'}</option>
            </>
          )}
        </select>
      </label>
      {market !== 'ml' && (
        <label className="flex flex-col gap-1 text-[13px] text-ink-2">
          {total ? 'Total' : 'Spread point for your side'}
          <input className={field} inputMode="decimal" value={line} onChange={(e) => setLine(e.target.value)} placeholder={total ? '44.5' : '−3.5'} />
        </label>
      )}
      <div className="flex flex-col gap-1 text-[13px] text-ink-2">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="bet-price">Price</label>
          <div role="radiogroup" aria-label="Price format" className="inline-flex rounded border border-line text-[12px]">
            {(['american', 'cents'] as const).map((m) => (
              <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)} className={`px-2 py-0.5 ${mode === m ? 'bg-accent/20 font-medium text-ink' : 'text-ink-2'}`}>
                {m === 'american' ? 'American' : 'Cents'}
              </button>
            ))}
          </div>
        </div>
        <input id="bet-price" className={field} inputMode="decimal" value={priceText} onChange={(e) => setPriceText(e.target.value)} placeholder={mode === 'american' ? '−245' : '70'} />
        {mode === 'cents' && asAmerican != null && validPrice(asAmerican) && <span className="text-ink-3">= {american(asAmerican)}</span>}
      </div>
      <label className="flex flex-col gap-1 text-[13px] text-ink-2">
        Stake ($)
        <input className={field} inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-[13px] text-ink-2">
        Fee ($, if any)
        <input className={field} inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} placeholder="0" />
      </label>
      <label className="flex flex-col gap-1 text-[13px] text-ink-2">
        Venue
        <input className={field} list="bet-venues" value={venue} onChange={(e) => setVenue(e.target.value)} />
        <datalist id="bet-venues">
          {VENUES.map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
      </label>
      <div className="flex flex-col justify-end gap-2 sm:col-span-2 lg:col-span-3">
        {error && (
          <p role="alert" className="text-[13px] text-[var(--critical)]">{error}</p>
        )}
        <div>
          <button type="submit" className="rounded border border-line bg-surface-2 px-3 py-1 text-[14px] font-medium text-ink hover:bg-accent/20">
            Add to my log
          </button>
        </div>
      </div>
    </form>
  )
}
