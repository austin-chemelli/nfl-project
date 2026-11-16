import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'

/**
 * A mask-image fade on each edge of a horizontally scrolling row that has more to scroll, so a phone
 * reader sees the row continues (the main nav, and every tab row). `key` re-runs the "keep the active
 * item in view" step: the pathname for the nav, the active tab for a tab row.
 */
export function useScrollFade<T extends HTMLElement>(key: unknown, activeSelector: string): { ref: React.RefObject<T | null>; style: CSSProperties | undefined } {
  const ref = useRef<T>(null)
  const [edges, setEdges] = useState({ left: false, right: false })
  const measure = useCallback(() => {
    const el = ref.current
    if (!el) return
    const left = el.scrollLeft > 1
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
    setEdges((e) => (e.left === left && e.right === right ? e : { left, right }))
  }, [])
  useEffect(() => {
    const el = ref.current
    if (!el) return
    measure()
    el.addEventListener('scroll', measure, { passive: true })
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    ro?.observe(el)
    return () => {
      el.removeEventListener('scroll', measure)
      ro?.disconnect()
    }
  }, [measure])
  useEffect(() => {
    ref.current?.querySelector(activeSelector)?.scrollIntoView?.({ inline: 'nearest', block: 'nearest' })
  }, [key, activeSelector])
  const stops = [edges.left ? 'transparent, #000 24px' : '#000, #000', edges.right ? '#000 calc(100% - 24px), transparent' : '#000, #000'].join(', ')
  const style = edges.left || edges.right ? { maskImage: `linear-gradient(to right, ${stops})`, WebkitMaskImage: `linear-gradient(to right, ${stops})` } : undefined
  return { ref, style }
}
