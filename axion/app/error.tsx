'use client'

import { useEffect } from 'react'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Surface the error for local debugging; in production this is where an
    // error-reporting integration would go.
    console.error(error)
  }, [error])

  return (
    <div className="cg-grid flex min-h-screen flex-col items-center justify-center px-6 py-10 text-center">
      <div className="w-full max-w-xl border-[1.5px] border-ink bg-paper px-8 py-10 text-left">
        <span className="cg-overline text-ink">SYSTEM INTERRUPT</span>
        <h1 className="cg-display mt-3 text-3xl text-ink">
          Something went wrong
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          The workspace hit an unexpected error. This is usually a temporary
          rendering issue — the underlying research data has not been affected.
        </p>
        <button
          onClick={reset}
          className="mt-6 border border-ink/40 bg-transparent px-5 py-2 text-sm font-medium text-ink transition-colors duration-150 hover:border-ink hover:bg-ink/5 focus-visible:border-ink focus-visible:ring-ink/15 focus-visible:ring-[3px] focus-visible:outline-none"
        >
          Try again
        </button>
      </div>
    </div>
  )
}
