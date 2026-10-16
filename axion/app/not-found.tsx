import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-black px-6 text-center">
      <p className="font-mono text-4xl font-bold text-[#3b82f6]">404</p>
      <h1 className="text-lg font-semibold text-[#f0f6ff]">Page not found</h1>
      <p className="max-w-md text-sm text-[#94a3b8]">
        That route doesn&apos;t exist in the Axion workspace.
      </p>
      <Link
        href="/"
        className="rounded-lg border border-[#3b82f6]/30 bg-[#3b82f6]/10 px-4 py-2 text-sm text-[#60a5fa] transition-colors hover:bg-[#3b82f6]/20 hover:text-white"
      >
        Back to workspace
      </Link>
    </div>
  )
}
