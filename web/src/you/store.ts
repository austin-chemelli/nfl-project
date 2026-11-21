/**
 * The reader's own approach (ADR 0034, M30): one saved weighting per browser, in localStorage only
 * (no accounts, nothing sent anywhere). Validated on load; tied to the group registry it was saved
 * under, so a saved approach from an older registry maps what still exists (see `migrate`).
 */
import { useSyncExternalStore } from 'react'
import type { GroupWeights } from '../diy'

export const YOU_KEY = 'nfl-you-v1'
export const DEFAULT_NAME = 'You'
export const NAME_MAX = 24

/** The calibration (p = σ(a·Σ W c + c·g)) fitted in the browser on every season of the matrix named `key`. */
export interface SavedCalib {
  key: string
  a: number
  c: number
}

export interface SavedApproach {
  v: 1
  name: string
  /** signed attention points per group, as on the Build sliders */
  points: GroupWeights
  /** the registry version and its weighted groups when saved */
  registry: string
  groups: string[]
  calib: SavedCalib | null
  saved_at: string
  /** lead with this line instead of the Student wherever the site shows a headline */
  is_default: boolean
}

const finite = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x)

/** A stored value -> a SavedApproach, or null when it isn't one (corrupt, foreign, future version). */
export function clean(v: unknown): SavedApproach | null {
  if (v == null || typeof v !== 'object' || Array.isArray(v)) return null
  const x = v as Record<string, unknown>
  if (x.v !== 1 || typeof x.registry !== 'string' || typeof x.saved_at !== 'string') return null
  if (x.points == null || typeof x.points !== 'object' || Array.isArray(x.points)) return null
  const points: GroupWeights = {}
  for (const [g, p] of Object.entries(x.points as Record<string, unknown>)) {
    if (finite(p)) points[g] = Math.max(-100, Math.min(100, p))
  }
  const groups = Array.isArray(x.groups) ? x.groups.filter((g): g is string => typeof g === 'string') : Object.keys(points)
  const c = x.calib as Record<string, unknown> | null | undefined
  const calib = c && typeof c.key === 'string' && finite(c.a) && finite(c.c) ? { key: c.key, a: c.a, c: c.c } : null
  return {
    v: 1,
    name: cleanName(x.name),
    points,
    registry: x.registry,
    groups,
    calib,
    saved_at: x.saved_at,
    is_default: x.is_default === true,
  }
}

export function cleanName(n: unknown): string {
  const s = typeof n === 'string' ? n.replace(/\s+/g, ' ').trim().slice(0, NAME_MAX) : ''
  return s || DEFAULT_NAME
}

let cache: SavedApproach | null | undefined
const listeners = new Set<() => void>()

function load(): SavedApproach | null {
  try {
    const raw = localStorage.getItem(YOU_KEY)
    return raw ? clean(JSON.parse(raw)) : null
  } catch {
    return null // storage blocked or a corrupt value: nothing saved
  }
}

export function getSaved(): SavedApproach | null {
  if (cache === undefined) cache = load()
  return cache
}

function write(next: SavedApproach | null) {
  cache = next
  try {
    if (next == null) localStorage.removeItem(YOU_KEY)
    else localStorage.setItem(YOU_KEY, JSON.stringify(next))
  } catch {
    // storage blocked: the approach lasts for this page view
  }
  for (const l of listeners) l()
}

function onStorage(e: StorageEvent) {
  if (e.key !== YOU_KEY && e.key !== null) return
  cache = load()
  for (const l of listeners) l()
}

function subscribe(l: () => void) {
  listeners.add(l)
  if (listeners.size === 1) window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(l)
    if (listeners.size === 0) window.removeEventListener('storage', onStorage)
  }
}

/** The saved approach in this browser (null if none); re-renders on a change here or in another tab. */
export function useSaved(): SavedApproach | null {
  return useSyncExternalStore(subscribe, getSaved, getSaved)
}

/** Save (or replace) the approach. Keeps the default flag and the name unless given. */
export function saveApproach(a: Omit<SavedApproach, 'v' | 'saved_at' | 'is_default' | 'name'> & { name?: string; is_default?: boolean }, now: Date = new Date()) {
  const cur = getSaved()
  write({
    v: 1,
    name: cleanName(a.name ?? cur?.name),
    points: { ...a.points },
    registry: a.registry,
    groups: [...a.groups],
    calib: a.calib,
    saved_at: now.toISOString(),
    is_default: a.is_default ?? cur?.is_default ?? false,
  })
}

/** Change fields of the saved approach without re-saving its weights (name, default, calibration). */
export function updateSaved(patch: Partial<Pick<SavedApproach, 'name' | 'is_default' | 'calib'>>) {
  const cur = getSaved()
  if (!cur) return
  write({ ...cur, ...patch, name: cleanName(patch.name ?? cur.name) })
}

export const setDefault = (on: boolean) => updateSaved({ is_default: on })
export const clearSaved = () => write(null)

export interface Migration {
  /** points restricted to the groups that exist now */
  points: GroupWeights
  /** groups with points that the current registry no longer has */
  dropped: string[]
  /** weighted groups the current registry has that the saved approach never saw (they start at 0) */
  added: string[]
  /** saved under a different registry version */
  changed: boolean
}

/** Map a saved approach onto the current registry's weighted groups. */
export function migrate(saved: Pick<SavedApproach, 'points' | 'groups' | 'registry'>, groups: string[], registry: string): Migration {
  const now = new Set(groups)
  const points: GroupWeights = {}
  const dropped: string[] = []
  for (const [g, p] of Object.entries(saved.points)) {
    if (now.has(g)) points[g] = p
    else if (p !== 0) dropped.push(g)
  }
  const seen = new Set(saved.groups)
  const added = saved.registry === registry ? [] : groups.filter((g) => !seen.has(g))
  return { points, dropped, added, changed: saved.registry !== registry }
}

/** Tests only: forget the in-memory copy so the next read comes from storage. */
export function resetSavedCache() {
  cache = undefined
}
