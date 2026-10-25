import Image from 'next/image'

export default function Loading() {
  return (
    <div className="cg-grid flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <Image
          src="/axion-logo.png"
          alt="AXION — Scientific Intelligence System"
          width={1672}
          height={941}
          priority
          className="h-16 w-auto object-contain"
        />
        <span className="cg-overline text-ink-muted">AXION SYSTEM</span>
        <span className="cg-mono-meta animate-pulse text-xs text-ink-soft">
          Loading workspace…
        </span>
      </div>
    </div>
  )
}
