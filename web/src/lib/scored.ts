/** Whether a feature is in the line (a member of a group the approaches score) or shown as context (ADR 0031). */
import type { Meta } from '../data/contract'
import { memberOf } from './meta'

/** The registry's feature name for a per-situation matchup edge. */
export const splitFeature = (split: string) => `matchup.edge_${split}`

/** In the line: a registry member of a group that is not context-only. Unknown features are not scored. */
export function isScored(feature: string, meta: Meta): boolean {
  const m = memberOf(meta, feature)
  if (!m) return false
  return meta.groups.groups.find((g) => g.id === m.group)?.context_only !== true
}
