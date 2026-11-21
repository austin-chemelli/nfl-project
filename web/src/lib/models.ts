/**
 * Model identity: order, colors (CSS variables from the palette), line style. `you` is the reader's
 * own line (ADR 0034): scored in this browser, never published; it is in a page's data only when the
 * reader saved one, so loops that keep the approaches a game has pick it up with no change.
 */
export const APPROACHES = ['traditionalist', 'analyst', 'sharp', 'student', 'you'] as const
export type ApproachId = (typeof APPROACHES)[number]
/** The site's headline line (D5): the server's and the default. Pages read `useHeadline()`, which is the reader's own line when they made it their default. */
export const HEADLINE = 'student'
export const REFERENCES = ['market_baseline', 'elo_v0', 'home_naive'] as const

export const isReference = (modelId: string) => (REFERENCES as readonly string[]).includes(modelId)
/** A line the site shows: the data may carry diagnostics too, and a list built from the file would show them. */
export const isPublicLine = (modelId: string) => (APPROACHES as readonly string[]).includes(modelId) || isReference(modelId)

export function colorVar(modelId: string): string {
  if ((APPROACHES as readonly string[]).includes(modelId)) return `var(--series-${modelId})`
  if (modelId === 'market_baseline') return 'var(--series-market)'
  return 'var(--series-ref)'
}

export function dashArray(modelId: string): string | undefined {
  if (modelId === 'home_naive') return '9 3' // Elo and the home line share a colour, so the dash tells them apart
  return modelId === 'elo_v0' || modelId === 'global' ? '4 3' : undefined
}

export const SHORT: Record<string, string> = {
  traditionalist: 'Traditionalist', analyst: 'Analyst', sharp: 'Sharp', student: 'Student', you: 'You',
  market_baseline: 'Market', elo_v0: 'Elo', home_naive: 'Home 57%', global: 'Global fit',
}

/** The reader's saved name for their own line (YouProvider calls this when it resolves the saved approach). */
export function setYouName(name: string) {
  SHORT.you = name
}

/** "The Student", "The Sharp"; the reader's own line goes by its saved name ("You" by default). */
export const theName = (modelId: string) => (modelId === 'you' ? SHORT.you : `The ${SHORT[modelId] ?? modelId}`)
/** Lower-case "the Student" inside a sentence; the reader's own line by its name. */
export const theNameLower = (modelId: string) => (modelId === 'you' ? SHORT.you : `the ${SHORT[modelId] ?? modelId}`)
/** A line that exists only in this browser (never locked, graded or published). */
export const isUnofficial = (modelId: string) => modelId === 'you'
