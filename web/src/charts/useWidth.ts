import { useEffect, useRef, useState } from 'react'

/** Track an element's width so SVG charts reflow on resize (no fixed pixel widths). */
export function useWidth<T extends HTMLElement = HTMLDivElement>(fallback = 640) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}
