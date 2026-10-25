'use client'

import * as React from 'react'
import * as SliderPrimitive from '@radix-ui/react-slider'

import { cn } from '@/lib/utils'

function Slider({
  className,
  defaultValue,
  value,
  min = 0,
  max = 100,
  thumbLabels,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root> & {
  /** Accessible names for each thumb, in value order. */
  thumbLabels?: string[]
}) {
  const rootLabel =
    typeof props['aria-label'] === 'string' ? props['aria-label'] : undefined
  const _values = React.useMemo(
    () =>
      Array.isArray(value)
        ? value
        : Array.isArray(defaultValue)
          ? defaultValue
          : [min, max],
    [value, defaultValue, min, max],
  )

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      defaultValue={defaultValue}
      value={value}
      min={min}
      max={max}
      className={cn(
        'relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50 data-[orientation=vertical]:h-full data-[orientation=vertical]:min-h-44 data-[orientation=vertical]:flex-col',
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className="bg-ink/15 relative grow overflow-hidden data-[orientation=horizontal]:h-[3px] data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-[3px]"
      >
        <SliderPrimitive.Range
          data-slot="slider-range"
          className="bg-ink absolute data-[orientation=horizontal]:h-full data-[orientation=vertical]:w-full"
        />
      </SliderPrimitive.Track>
      {Array.from({ length: _values.length }, (_, index) => (
        <SliderPrimitive.Thumb
          data-slot="slider-thumb"
          key={index}
          aria-label={
            thumbLabels?.[index] ??
            (rootLabel
              ? `${rootLabel}${_values.length > 1 ? ` (${index + 1} of ${_values.length})` : ''}`
              : `Slider value ${index + 1}`)
          }
          className="focus-visible:ring-ink/20 block size-3.5 shrink-0 border-[1.5px] border-ink bg-paper transition-colors duration-150 hover:bg-ink hover:border-ink focus-visible:border-ink focus-visible:ring-[3px] focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
        />
      ))}
    </SliderPrimitive.Root>
  )
}

export { Slider }
