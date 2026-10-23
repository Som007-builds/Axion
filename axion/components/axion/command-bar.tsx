'use client'

import { useState, useRef, useEffect } from 'react'
import { Search, ArrowRight, Clock, Loader2 } from 'lucide-react'

interface CommandBarProps {
  onSubmit: (query: string) => void
  recentQueries?: string[]
  isLoading?: boolean
}

export function CommandBar({ onSubmit, recentQueries = [], isLoading }: CommandBarProps) {
  const [value, setValue] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [showRecent, setShowRecent] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // ⌘K / Ctrl+K keyboard shortcut
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (value.trim() && !isLoading) {
      onSubmit(value.trim())
      setValue('')
      setShowRecent(false)
      inputRef.current?.blur()
    }
  }

  function handleRecentSelect(query: string) {
    onSubmit(query)
    setValue('')
    setShowRecent(false)
    inputRef.current?.blur()
  }

  return (
    <div className="relative">
      <form onSubmit={handleSubmit} role="search" className="relative">
        <div
          className={`
            relative flex items-center border bg-paper transition-colors duration-150
            ${isFocused
              ? 'border-ink ring-[3px] ring-ink/15'
              : 'border-ink/40 hover:border-ink/70'
            }
          `}
        >
          <div className="flex items-center pl-3.5">
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-ink" aria-hidden="true" />
            ) : (
              <Search className="h-4 w-4 text-ink/50" aria-hidden="true" />
            )}
          </div>
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onFocus={() => { setIsFocused(true); setShowRecent(true) }}
            onBlur={() => { setIsFocused(false); setTimeout(() => setShowRecent(false), 200) }}
            placeholder="Ask a research question across your knowledge graph..."
            aria-label="Ask a research question"
            disabled={isLoading}
            className="h-11 min-w-0 flex-1 bg-transparent px-3 text-[15px] text-ink placeholder:text-ink/35 focus:outline-none disabled:opacity-60"
          />
          <div className="flex items-center gap-2 pr-2.5">
            {!isFocused && !value && (
              <kbd className="cg-mono-meta hidden items-center gap-0.5 border border-ink/30 px-1.5 py-0.5 text-[10px] text-ink/50 sm:flex">
                ⌘K
              </kbd>
            )}
            {value && (
              <button
                type="submit"
                aria-label="Submit research query"
                disabled={isLoading}
                className="flex h-7 w-7 items-center justify-center bg-ink text-paper transition-colors duration-150 hover:bg-ink-soft disabled:opacity-50 focus-visible:outline-none"
              >
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </form>

      {/* Recent Queries Dropdown */}
      {showRecent && recentQueries.length > 0 && !value && (
        <div
          role="listbox"
          aria-label="Recent queries"
          className="animate-fade-up absolute left-0 right-0 top-full z-50 mt-1 border border-ink/40 bg-paper p-1"
        >
          <div className="px-3 pt-2 pb-1.5">
            <span className="cg-overline text-ink/50">Recent</span>
          </div>
          {recentQueries.slice(0, 5).map((query, i) => (
            <button
              key={i}
              role="option"
              aria-selected={false}
              onClick={() => handleRecentSelect(query)}
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm text-ink-soft transition-colors duration-100 hover:bg-ink/5 hover:text-ink focus-visible:outline-none"
            >
              <Clock className="h-3.5 w-3.5 shrink-0 text-ink/40" aria-hidden="true" />
              <span className="min-w-0 truncate">{query}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
