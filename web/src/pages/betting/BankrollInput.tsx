import { useId, useState } from 'react'
import { setBankroll, useBankroll } from '../../lib/bankroll'

/** The visitor's bankroll, kept in this browser only; sits in the summary strip's "Your stake" tile. */
export function BankrollInput() {
  const id = useId()
  const bankroll = useBankroll()
  const [text, setText] = useState(bankroll == null ? '' : String(bankroll))
  return (
    <span className="flex items-center gap-1">
      <label htmlFor={id} className="sr-only">
        Your bankroll
      </label>
      <span aria-hidden="true" className="text-ink-3">
        $
      </span>
      <input
        id={id}
        type="number"
        min="0"
        step="any"
        inputMode="decimal"
        placeholder="Bankroll"
        title="Kept in this browser only."
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          const n = Number(e.target.value)
          setBankroll(e.target.value.trim() !== '' && Number.isFinite(n) && n > 0 ? n : null)
        }}
        className="w-full min-w-0 rounded border border-line bg-surface-0 px-2 py-0.5 text-base font-semibold outline-none focus:border-[var(--accent)]"
      />
    </span>
  )
}
