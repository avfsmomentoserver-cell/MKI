import { useEffect, useState } from 'react'

export type Theme = 'dark' | 'light'

const KEY = 'mkc.theme'

function readTheme(): Theme {
  try {
    return window.localStorage.getItem(KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function initTheme(): void {
  const t = readTheme()
  const el = document.documentElement
  el.classList.toggle('dark', t === 'dark')
  el.style.colorScheme = t
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(readTheme)
  const toggle = () =>
    setTheme((t) => {
      const next: Theme = t === 'dark' ? 'light' : 'dark'
      document.documentElement.classList.toggle('dark', next === 'dark')
      document.documentElement.style.colorScheme = next
      try {
        window.localStorage.setItem(KEY, next)
      } catch {
        // storage blocked: the toggle still works for this page view
      }
      return next
    })
  useEffect(() => {
    // Re-apply on mount so a storage change in another tab or a manual
    // class edit (e.g. index.html default) wins over a stale state value.
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])
  return [theme, toggle]
}
