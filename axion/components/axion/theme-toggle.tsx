'use client'

import { Monitor, Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTheme, type ThemePreference } from '@/components/theme-provider'

const OPTIONS: Array<{
  value: ThemePreference
  label: string
  icon: React.ComponentType<{ className?: string }>
}> = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, resolvedTheme, mounted, setTheme } = useTheme()

  return (
    <div
      role="group"
      aria-label={`Colour theme${mounted ? `, currently ${theme}` : ''}`}
      className={cn(
        'inline-flex shrink-0 items-center border border-ink/25 bg-paper p-0.5',
        className,
      )}
    >
      {OPTIONS.map((option) => {
        const Icon = option.icon
        const active = mounted && theme === option.value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setTheme(option.value)}
            aria-pressed={active}
            aria-label={`${option.label} theme`}
            title={`${option.label} theme`}
            className={cn(
              'flex h-6 w-6 items-center justify-center transition-colors duration-150 focus-visible:outline-none',
              active
                ? 'bg-ink text-paper'
                : 'text-ink-muted hover:bg-ink/5 hover:text-ink',
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {option.value === 'system' && active && (
              <span className="sr-only">
                (resolved to {resolvedTheme})
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
