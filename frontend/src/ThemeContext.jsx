import { createContext, useContext, useState, useCallback } from 'react'

const ThemeContext = createContext()

function getTheme() {
  try {
    const stored = localStorage.getItem('theme')
    if (stored === 'dark' || stored === 'light') return stored
  } catch {}
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

function applyTheme(t) {
  const root = document.documentElement
  root.classList.toggle('dark', t === 'dark')
  try { localStorage.setItem('theme', t) } catch {}
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const t = getTheme()
    applyTheme(t)
    return t
  })

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark'
      applyTheme(next)
      return next
    })
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
