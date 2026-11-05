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

/** The groups wave 2 zeroed (D7), for meta.json files published before `context_only`. Delete once production's has it. */
const CONTEXT_ONLY = new Set(['coaching', 'off_scheme', 'def_scheme', 'matchups'])

/** A group shown as context (Tendencies, Details) that carries no weight in the Preview's bars. */
export function isContextOnly(meta: Meta, id: string): boolean {
  return groupOf(meta, id)?.context_only === true || CONTEXT_ONLY.has(id)
}

/** Description for a feature id or a group id (hover help). */
export function helpFor(meta: Meta, id: string): string {
  return memberOf(meta, id)?.description ?? groupOf(meta, id)?.description ?? ''
}

export function approachOf(meta: Meta, id: string) {
  return meta.approaches.find((a) => a.id === id)
}
