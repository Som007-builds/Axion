'use client'

import { useEffect } from 'react'
import { AlertTriangle } from 'lucide-react'

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
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-black px-6 text-center">
      <AlertTriangle className="h-10 w-10 text-[#f43f5e]" />
      <h1 className="text-lg font-semibold text-[#f0f6ff]">Something went wrong</h1>
      <p className="max-w-md text-sm text-[#94a3b8]">
        The workspace hit an unexpected error. This is usually a temporary API or
        rendering issue.
      </p>
      <button
        onClick={reset}
        className="rounded-lg border border-[#3b82f6]/30 bg-[#3b82f6]/10 px-4 py-2 text-sm text-[#60a5fa] transition-colors hover:bg-[#3b82f6]/20 hover:text-white"
      >
        Try again
      </button>
    </div>
  )
}
