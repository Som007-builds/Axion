export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-black">
      <div className="flex items-center gap-3 text-[#94a3b8]">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#3b82f6] border-t-transparent" />
        <span className="font-mono text-xs">Loading Axion…</span>
      </div>
    </div>
  )
}
