'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'axion-theme'

interface ThemeContextValue {
  theme: ThemePreference
  resolvedTheme: ResolvedTheme
  mounted: boolean
  setTheme: (theme: ThemePreference) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function prefersDark(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

function resolve(theme: ThemePreference): ResolvedTheme {
  return theme === 'dark' || (theme === 'system' && prefersDark()) ? 'dark' : 'light'
}

function readStoredTheme(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      return stored
    }
  } catch {
    // Storage can be unavailable in private/embedded contexts.
  }
  return 'system'
}

function applyTheme(theme: ThemePreference): ResolvedTheme {
  const resolved = resolve(theme)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.dataset.theme = theme
  root.style.colorScheme = resolved
  return resolved
}

const subscribeToMount = () => () => {}
const getMountedSnapshot = () => true
const getServerMountedSnapshot = () => false

export function ThemeProvider({ children }: { children: ReactNode }) {
  // The pre-hydration script has already applied the stored preference to
  // <html>. Initialising from the same source keeps the provider in sync with
  // that first paint; the toggle only reveals state after hydration.
  const [theme, setThemeState] = useState<ThemePreference>(() =>
    typeof window === 'undefined' ? 'system' : readStoredTheme(),
  )
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolve(theme))
  const mounted = useSyncExternalStore(
    subscribeToMount,
    getMountedSnapshot,
    getServerMountedSnapshot,
  )

  useEffect(() => {
    function onSystemChange() {
      if (readStoredTheme() === 'system') {
        setResolvedTheme(applyTheme('system'))
      }
    }
    function onStorage(event: StorageEvent) {
      if (event.key !== THEME_STORAGE_KEY) return
      const next = readStoredTheme()
      setThemeState(next)
      setResolvedTheme(applyTheme(next))
    }

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', onSystemChange)
    window.addEventListener('storage', onStorage)
    return () => {
      media.removeEventListener('change', onSystemChange)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next)
    setResolvedTheme(applyTheme(next))
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // The applied theme still works for this session.
    }
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, mounted, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) {
    throw new Error('useTheme must be used inside ThemeProvider')
  }
  return value
}
