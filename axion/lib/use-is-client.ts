'use client'

import { useSyncExternalStore } from 'react'

const emptySubscribe = () => () => {}

/**
 * Returns `false` during SSR and the first client render, then `true` after
 * hydration completes.
 *
 * This replaces the common hydration guard
 *   `const [mounted, setMounted] = useState(false); useEffect(() => setMounted(true), [])`
 * which trips the `react-hooks/set-state-in-effect` rule.
 */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    emptySubscribe,
    () => true, // client snapshot
    () => false, // server snapshot
  )
}
