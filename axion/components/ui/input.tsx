import * as React from 'react'

import { cn } from '@/lib/utils'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'placeholder:text-ink/40 bg-paper border-ink/40 text-ink h-9 w-full min-w-0 border px-3 py-1 text-base transition-colors duration-150 outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium hover:border-ink/70 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm',
        'focus-visible:border-ink focus-visible:ring-ink/15 focus-visible:ring-[3px]',
        'aria-invalid:border-[1.5px] aria-invalid:border-ink',
        className,
      )}
      {...props}
    />
  )
}

export { Input }
