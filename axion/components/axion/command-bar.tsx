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
  const [placeholder, setPlaceholder] = useState('Ask a research question...')
  const inputRef = useRef<HTMLInputElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  // Escape closes the list and moves focus back to the input. That focus event
  // must not immediately reopen the list it just dismissed.
  const suppressRecentOpenRef = useRef(false)

  // The theme switch shares the top row, so the full prompt truncates on
  // narrow phones. Swap in a shorter prompt below the sm breakpoint.
  useEffect(() => {
    const media = window.matchMedia('(max-width: 639px)')
    const update = () =>
      setPlaceholder(media.matches ? 'Ask…' : 'Ask a research question...')
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

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
    <div
      ref={rootRef}
      className="relative"
      onBlur={(event) => {
        if (
          !(event.relatedTarget instanceof Node) ||
          !event.currentTarget.contains(event.relatedTarget)
        ) {
          setShowRecent(false)
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          setShowRecent(false)
          suppressRecentOpenRef.current = true
          inputRef.current?.focus()
          window.setTimeout(() => {
            suppressRecentOpenRef.current = false
          }, 0)
        }
      }}
    >
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
              <Search className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            )}
          </div>
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onFocus={() => {
              setIsFocused(true)
              if (!suppressRecentOpenRef.current) setShowRecent(true)
            }}
            onBlur={() => setIsFocused(false)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                setShowRecent(false)
                return
              }
              if (
                event.key === 'ArrowDown' &&
                showRecent &&
                recentQueries.length > 0
              ) {
                event.preventDefault()
                rootRef.current
                  ?.querySelector<HTMLButtonElement>('[role="option"]')
                  ?.focus()
              }
            }}
            placeholder={placeholder}
            aria-label="Ask a research question"
            role="combobox"
            aria-autocomplete="list"
            aria-haspopup="listbox"
            aria-expanded={showRecent && recentQueries.length > 0}
            aria-controls={showRecent && recentQueries.length > 0 ? 'recent-queries' : undefined}
            disabled={isLoading}
            className="h-11 min-w-0 flex-1 bg-transparent px-3 text-[15px] text-ink placeholder:text-ink-muted focus:outline-none disabled:opacity-60"
          />
          <div className="flex items-center gap-2 pr-2.5">
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
          id="recent-queries"
          role="listbox"
          aria-label="Recent queries"
          className="animate-fade-up absolute left-0 right-0 top-full z-50 mt-1 border border-ink/40 bg-paper p-1"
        >
          <div className="px-3 pt-2 pb-1.5">
            <span className="cg-overline text-ink-muted">Recent</span>
          </div>
          {recentQueries.slice(0, 5).map((query, i) => (
            <button
              key={i}
              role="option"
              aria-selected={false}
              disabled={isLoading}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => handleRecentSelect(query)}
              className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm text-ink-soft transition-colors duration-100 hover:bg-ink/5 hover:text-ink disabled:opacity-50"
            >
              <Clock className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
              <span className="min-w-0 truncate">{query}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
