/** Who can reach each part of the betting guide (ADR 0033). */
export type Visibility = 'public' | 'unlisted' | 'dev'

/**
 * ADR 0033 / decision 3 of the round plan, default (b): the math public, the weekly card and the bet log
 * unlisted. One line to change each.
 * - `public`: routed and in the nav.
 * - `unlisted`: routed in production (reachable by URL) but in no nav or link on public pages, and the page asks search engines to skip it.
 * - `dev`: only in `npm run dev` (a NotFound in production), like hiddenPages.ts.
 */
export const BETTING_VISIBILITY: Record<'math' | 'card' | 'log', Visibility> = { math: 'public', card: 'unlisted', log: 'unlisted' }

/** Can this part be opened by URL? Everything can in development. */
export const reachable = (v: Visibility): boolean => import.meta.env.DEV || v !== 'dev'

/** Does this part appear in the nav and in links on public pages? Everything does in development. */
export const listed = (v: Visibility): boolean => import.meta.env.DEV || v === 'public'
