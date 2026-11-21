/**
 * A value kept in this browser only (localStorage, no accounts), readable with useSyncExternalStore.
 * The pattern of picks.ts: an in-memory copy, a `storage` listener for other tabs, and every storage
 * call in try/catch (blocked storage or a corrupt value starts empty; the value then lasts for the page view).
 */
import { useSyncExternalStore } from 'react'

export function createStore<T>(key: string, empty: T, parse: (raw: unknown) => T) {
  let cache: T | null = null
  const listeners = new Set<() => void>()

  function load(): T {
    try {
      const raw = localStorage.getItem(key)
      return raw == null ? empty : parse(JSON.parse(raw))
    } catch {
      return empty
    }
  }

  const get = (): T => {
    if (cache == null) cache = load()
    return cache
  }

  function set(next: T) {
    cache = next
    try {
      localStorage.setItem(key, JSON.stringify(next))
    } catch {
      // storage blocked: the value lasts for this page view
    }
    for (const l of listeners) l()
  }

  function onStorage(e: StorageEvent) {
    if (e.key !== key && e.key !== null) return
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

  return {
    key,
    get,
    set,
    use: () => useSyncExternalStore(subscribe, get, get),
    /** Tests only: forget the in-memory copy so the next read comes from storage. */
    reset: () => {
      cache = null
    },
  }
}
