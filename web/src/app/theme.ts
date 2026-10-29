/** Light/dark/system theme on <html data-theme>. The CSS tokens do the rest. */
import { useEffect, useState } from 'react'

export type Theme = 'system' | 'light' | 'dark'
const KEY = 'nfl-theme'

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(read)
  useEffect(() => {
    const el = document.documentElement
    if (theme === 'system') el.removeAttribute('data-theme')
    else el.setAttribute('data-theme', theme)
    try {
      if (theme === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, theme)
    } catch {
      // storage blocked: the choice lasts for this page view
    }
  }, [theme])
  return [theme, setTheme] as const
}
