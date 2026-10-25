import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="cg-grid flex min-h-screen flex-col items-center justify-center px-6 py-10 text-center">
      <div className="w-full max-w-xl border border-ink/40 bg-paper px-8 py-10 text-left">
        <span className="cg-overline text-ink-muted">ERROR 404</span>
        <p className="cg-display mt-3 text-5xl text-ink">404</p>
        <h1 className="cg-display mt-2 text-2xl text-ink">Page not found</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          That route doesn&apos;t exist in the Axion workspace.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block border border-ink/40 bg-transparent px-5 py-2 text-sm font-medium text-ink transition-colors duration-150 hover:border-ink hover:bg-ink/5 focus-visible:border-ink focus-visible:ring-ink/15 focus-visible:ring-[3px] focus-visible:outline-none"
        >
          Back to workspace
        </Link>
      </div>
    </div>
  )
}
