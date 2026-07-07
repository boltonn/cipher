"use client"

import * as React from "react"
import { ScrollArea as ScrollAreaPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

function setRef<T>(ref: React.Ref<T> | undefined, value: T) {
  if (typeof ref === "function") ref(value)
  else if (ref && typeof ref === "object")
    (ref as React.MutableRefObject<T>).current = value
}

function ScrollArea({
  className,
  viewportClassName,
  viewportRef,
  scrollFade,
  orientation = "vertical",
  scrollbarGutter = false,
  children,
  ...props
}: React.ComponentProps<typeof ScrollAreaPrimitive.Root> & {
  /** Extra className applied to the inner scrollable viewport, not the root. */
  viewportClassName?: string
  /** Ref to the inner scrollable viewport element (e.g. for virtualizers needing the real scroll container). */
  viewportRef?: React.Ref<HTMLDivElement | null>
  /** Fades content near the scrollable edges instead of a hard clip. */
  scrollFade?: boolean
  /** Which scrollbar(s) to render. @default "vertical" */
  orientation?: "vertical" | "horizontal" | "both"
  /**
   * Marks the viewport with `data-has-overflow-x`/`data-has-overflow-y` once content
   * actually overflows, so callers can reserve layout space for the scrollbar via a
   * `has-[[data-slot=scroll-area-viewport][data-has-overflow-x]]:...` selector.
   */
  scrollbarGutter?: boolean
}) {
  const internalViewportRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    if (!scrollbarGutter) return
    const viewport = internalViewportRef.current
    if (!viewport) return

    const updateOverflow = () => {
      viewport.toggleAttribute(
        "data-has-overflow-x",
        viewport.scrollWidth > viewport.clientWidth
      )
      viewport.toggleAttribute(
        "data-has-overflow-y",
        viewport.scrollHeight > viewport.clientHeight
      )
    }

    updateOverflow()
    const observer = new ResizeObserver(updateOverflow)
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [scrollbarGutter, children])

  return (
    <ScrollAreaPrimitive.Root
      data-slot="scroll-area"
      className={cn("relative", className)}
      {...props}
    >
      <ScrollAreaPrimitive.Viewport
        ref={(node) => {
          internalViewportRef.current = node
          setRef(viewportRef, node)
        }}
        data-slot="scroll-area-viewport"
        className={cn(
          "size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1",
          scrollFade &&
            "[mask-image:linear-gradient(to_bottom,transparent,black_12px,black_calc(100%-12px),transparent)]",
          viewportClassName
        )}
      >
        {children}
      </ScrollAreaPrimitive.Viewport>
      {(orientation === "vertical" || orientation === "both") && (
        <ScrollBar orientation="vertical" />
      )}
      {(orientation === "horizontal" || orientation === "both") && (
        <ScrollBar orientation="horizontal" />
      )}
      <ScrollAreaPrimitive.Corner />
    </ScrollAreaPrimitive.Root>
  )
}

function ScrollBar({
  className,
  orientation = "vertical",
  ...props
}: React.ComponentProps<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>) {
  return (
    <ScrollAreaPrimitive.ScrollAreaScrollbar
      data-slot="scroll-area-scrollbar"
      data-orientation={orientation}
      orientation={orientation}
      className={cn(
        "flex touch-none p-px transition-colors select-none data-horizontal:h-2.5 data-horizontal:flex-col data-horizontal:border-t data-horizontal:border-t-transparent data-vertical:h-full data-vertical:w-2.5 data-vertical:border-l data-vertical:border-l-transparent",
        className
      )}
      {...props}
    >
      <ScrollAreaPrimitive.ScrollAreaThumb
        data-slot="scroll-area-thumb"
        className="relative flex-1 rounded-full bg-border"
      />
    </ScrollAreaPrimitive.ScrollAreaScrollbar>
  )
}

export { ScrollArea, ScrollBar }
