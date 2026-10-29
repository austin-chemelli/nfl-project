import type { SeasonGame } from '../../diy'

export function resultText(g: Pick<SeasonGame, 'result' | 'home' | 'away'>): string {
  if (g.result == null) return '–'
  if (g.result === 0) return 'Tie'
  return `${g.result > 0 ? g.home : g.away} by ${Math.abs(g.result)}`
}
