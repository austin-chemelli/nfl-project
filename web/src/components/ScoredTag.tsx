/** A muted tag: is this number in the line, or only shown as context (ADR 0031)? Hover or focus for the sentence. */
const WORDS = {
  scored: { text: 'in the line', tip: 'The approaches weigh this.' },
  context: { text: 'shown, not scored', tip: "Context: it didn't earn a weight in the backtest." },
} as const

export function ScoredTag({ scored }: { scored: boolean }) {
  const w = scored ? WORDS.scored : WORDS.context
  return (
    <span
      tabIndex={0}
      title={w.tip}
      aria-label={`${w.text}: ${w.tip}`}
      data-testid="scored-tag"
      className="ml-2 whitespace-nowrap rounded-full border border-line px-1.5 py-px align-middle text-[11px] font-normal text-ink-3 focus:outline-2 focus:outline-accent"
    >
      {w.text}
    </span>
  )
}
