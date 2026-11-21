import { useEffect } from 'react'

/** Ask search engines to skip the page while it is mounted (unlisted pages). */
export function useNoindex(on = true) {
  useEffect(() => {
    if (!on) return
    const meta = document.createElement('meta')
    meta.name = 'robots'
    meta.content = 'noindex'
    document.head.appendChild(meta)
    return () => {
      meta.parentNode?.removeChild(meta)
    }
  }, [on])
}
