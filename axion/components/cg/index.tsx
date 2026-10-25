'use client'

import { cn } from '@/lib/utils'

// ── Cobalt Grid shared primitives ────────────────────────────────────────────
// Small, purpose-built components reused across every view. Everything here
// derives from the token system in globals.css: cream paper, cobalt ink,
// square corners, hairline rules. No colors, shadows, or radii beyond that.

/** Tracked uppercase technical label (Hanken Grotesk). */
export function Overline({
  children,
  className,
  as: Tag = 'span',
}: {
  children: React.ReactNode
  className?: string
  as?: 'span' | 'div' | 'h2' | 'h3' | 'h4' | 'p'
}) {
  return (
    <Tag className={cn('cg-overline text-ink-muted', className)}>{children}</Tag>
  )
}

/** Monospaced metadata value with tabular numerals. */
export function MonoData({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <span className={cn('cg-mono-meta text-ink font-medium', className)}>
      {children}
    </span>
  )
}

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export function confidenceLevel(value: number | undefined | null): ConfidenceLevel {
  if (value == null) return 'medium'
  if (value >= 0.8) return 'high'
  if (value >= 0.5) return 'medium'
  return 'low'
}

/**
 * Monochrome confidence encoding. Never color alone:
 * high = solid cobalt square, medium = outlined square, low = hatched square,
 * always paired with the numeric percentage and the level label.
 */
export function ConfidenceTag({
  value,
  showLabel = true,
  size = 'sm',
  className,
}: {
  value: number
  showLabel?: boolean
  size?: 'sm' | 'md'
  className?: string
}) {
  const level = confidenceLevel(value)
  const box =
    size === 'md'
      ? 'h-3 w-3 border-[1.5px]'
      : 'h-2 w-2 border'
  return (
    <span
      className={cn('inline-flex items-center gap-2', className)}
      title={`${Math.round(value * 100)}% confidence`}
    >
      <span
        aria-hidden="true"
        className={cn(
          'inline-block shrink-0',
          box,
          level === 'high' && 'border-ink bg-ink',
          level === 'medium' && 'border-ink bg-transparent',
          level === 'low' && 'cg-hatch border-ink',
        )}
      />
      <span className="cg-mono-meta text-ink text-xs font-medium tabular-nums">
        {Math.round(value * 100)}%
      </span>
      {showLabel && (
        <span className="cg-overline text-ink-muted">
          {level.toUpperCase()}
        </span>
      )}
    </span>
  )
}

/**
 * Status chip for fixed, small-vocabulary states (RESOLVED / ONGOING /
 * ACTIVE / FADING / COMPLETED / FAILED / QUEUED). Filled = terminal/positive,
 * outlined = active/uncertain, hatched = failure. Text always present.
 */
export function StatusChip({
  status,
  className,
}: {
  status:
    | 'resolved'
    | 'ongoing'
    | 'completed'
    | 'failed'
    | 'queued'
    | 'running'
    | 'active'
    | 'fading'
    | 'unknown'
  className?: string
}) {
  const filled = status === 'resolved' || status === 'completed'
  const hatched = status === 'failed'
  return (
    <span
      className={cn(
        'cg-overline inline-flex items-center gap-1.5 border px-2 py-0.5 text-ink',
        filled && 'border-ink bg-ink text-paper',
        !filled && !hatched && 'border-ink/50 bg-transparent',
        hatched && 'cg-hatch border-ink',
        className,
      )}
    >
      {!filled && (
        <span
          aria-hidden="true"
          className={cn(
            'inline-block h-2 w-2',
            hatched ? 'border border-ink' : 'border border-ink/70',
          )}
        />
      )}
      {status.toUpperCase()}
    </span>
  )
}

/** Thin structural divider. strong = 1.5px ink, default = 1px faint. */
export function Rule({ strong = false, className }: { strong?: boolean; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'w-full',
        strong ? 'cg-rule-strong' : 'border-t border-ink/20',
        className,
      )}
    />
  )
}

/** Icon-free constrained banner: overline heading + explanatory text. */
export function ErrorBanner({
  title = 'Data unavailable',
  message,
  className,
}: {
  title?: string
  message: string
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'border-[1.5px] border-ink bg-paper px-4 py-3',
        className,
      )}
    >
      <Overline className="text-ink">{title}</Overline>
      <p className="mt-1 text-sm leading-relaxed text-ink">{message}</p>
    </div>
  )
}

/** Calm empty state: square glyph, display title, one explanatory line. */
export function EmptyState({
  glyph = '·',
  title,
  description,
  action,
  glitch = false,
  className,
}: {
  glyph?: string
  title: string
  description: string
  action?: React.ReactNode
  glitch?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-start justify-center border border-ink/25 bg-paper px-8 py-12',
        className,
      )}
    >
      <div className="flex items-start gap-6">
        {glitch && <PixelGlitch className="mt-2 hidden sm:flex" />}
        <div className="min-w-0">
          <span aria-hidden="true" className="cg-mono-meta text-2xl leading-none text-ink">
            {glyph}
          </span>
          <h2 className="cg-display mt-3 text-2xl text-ink">{title}</h2>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-soft">
            {description}
          </p>
          {action && <div className="mt-5">{action}</div>}
        </div>
      </div>
    </div>
  )
}

/**
 * Pixel-glitch motif: stepped horizontal scanline fragments. Purely
 * decorative; hidden from assistive technology and never interactive.
 */
export function PixelGlitch({
  className,
  width = 'w-24',
}: {
  className?: string
  width?: string
}) {
  const rows: Array<{ w: string; o: string }> = [
    { w: 'w-full', o: 'bg-ink' },
    { w: 'w-3/5 ml-[20%]', o: 'bg-ink/70' },
    { w: 'w-4/5', o: 'bg-ink' },
    { w: 'w-2/5 ml-[60%]', o: 'bg-ink/40' },
    { w: 'w-full', o: 'bg-ink/90' },
    { w: 'w-1/4 ml-[70%]', o: 'bg-ink/50' },
    { w: 'w-3/5', o: 'bg-ink' },
  ]
  return (
    <div
      aria-hidden="true"
      className={cn('flex flex-col gap-[3px] py-1', width, className)}
    >
      {rows.map((row, i) => (
        <span key={i} className={cn('h-[3px] shrink-0', row.w, row.o)} />
      ))}
    </div>
  )
}

/**
 * QR-block mosaic: hand-authored square-cell punctuation, not a real code.
 * Decorative only; aria-hidden.
 */
export function QrBlock({ className }: { className?: string }) {
  // 6x6 hand-authored pattern
  const cells = [
    1, 1, 1, 0, 1, 0,
    1, 0, 1, 0, 0, 1,
    1, 1, 0, 1, 1, 0,
    0, 0, 1, 0, 1, 1,
    1, 0, 1, 1, 0, 1,
    1, 1, 0, 1, 0, 1,
  ]
  return (
    <div
      aria-hidden="true"
      className={cn(
        'grid h-8 w-8 shrink-0 grid-cols-6 gap-[2px] border border-ink/30 p-[2px]',
        className,
      )}
    >
      {cells.map((cell, i) => (
        <span
          key={i}
          className={cn(cell ? 'bg-ink' : 'bg-ink/10')}
        />
      ))}
    </div>
  )
}

/** Editorial page/section introduction block: overline + display title + copy. */
export function SectionIntro({
  kicker,
  title,
  description,
  right,
  className,
}: {
  kicker: string
  title: string
  description?: string
  right?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-end justify-between gap-6', className)}>
      <div className="min-w-0">
        <Overline>{kicker}</Overline>
        <h2 className="cg-display mt-2 text-3xl text-ink sm:text-4xl">{title}</h2>
        {description && (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-soft">
            {description}
          </p>
        )}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  )
}
