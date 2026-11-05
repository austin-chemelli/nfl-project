/** Lookups into meta.json: registry members, groups, tendency metrics, approaches. */
import type { Meta, Group, Member } from '../data/contract'

export function memberOf(meta: Meta, feature: string): (Member & { group: string; groupName: string }) | undefined {
  for (const g of meta.groups.groups) {
    const m = g.members.find((x) => x.feature === feature)
    if (m) return { ...m, group: g.id, groupName: g.name }
  }
  return undefined
}

export function groupOf(meta: Meta, id: string): Group | undefined {
  return meta.groups.groups.find((g) => g.id === id)
}

export function groupName(meta: Meta, id: string): string {
  return groupOf(meta, id)?.name ?? id.replace(/_/g, ' ')
}

/** A group shown as context (Tendencies, Details) that carries no weight in the Preview's bars. */
export function isContextOnly(meta: Meta, id: string): boolean {
  return groupOf(meta, id)?.context_only === true
}

/**
 * Whether a group's edge can be called one. Context groups carry no weight. Venue & weather only
 * shifts home advantage, and on a neutral site Rest & travel reads against a nominal home team, so
 * both show a lopsided "edge" for the away team that nobody earned: all 9 neutral games of 2026
 * did. The points they move are real; the percentile isn't a matchup edge.
 */
export function countsAsEdge(meta: Meta, id: string, neutral = false): boolean {
  return !isContextOnly(meta, id) && id !== 'venue_weather' && !(neutral && id === 'rest_travel')
}

/** A percentile as printed: "bigger than 100% of matchups" can't be true. */
export const edgePct = (p: number) => Math.min(99, Math.round(p))

/** Description for a feature id or a group id (hover help). */
export function helpFor(meta: Meta, id: string): string {
  return memberOf(meta, id)?.description ?? groupOf(meta, id)?.description ?? ''
}

export function approachOf(meta: Meta, id: string) {
  return meta.approaches.find((a) => a.id === id)
}
