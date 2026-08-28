"use client";

import { ColumnBreakpoint, useResponsiveColumns } from "@/hooks/use-responsive-columns";
import { cn } from "@/lib/utils";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ReactNode, useEffect, useRef, useState } from "react";

interface VirtualizedGridProps<T> {
  items: T[];
  breakpoints: ColumnBreakpoint[];
  getKey: (item: T, index: number) => string;
  renderItem: (item: T, index: number) => ReactNode;
  /** Rough initial row height guess in px before the real one is measured; only affects first paint. */
  estimatedRowHeight?: number;
  gapClassName?: string;
  className?: string;
}

/** Walks up from `el` to find the nearest ancestor that's set up to scroll its own content. */
function findScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null;
  while (node && node !== document.body) {
    const overflowY = getComputedStyle(node).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") return node;
    node = node.parentElement;
  }
  return null;
}

/**
 * Row-virtualized grid for long infinite-scroll lists -- only rows near the
 * viewport are ever mounted, so accumulating hundreds or thousands of items
 * via infinite scroll doesn't bog down/crash the tab. Scrolls with whichever
 * ancestor is actually the scroll container (this app's page shell scrolls
 * an inner `<main overflow-y-auto>`, not the window).
 */
export function VirtualizedGrid<T>({
  items,
  breakpoints,
  getKey,
  renderItem,
  estimatedRowHeight = 240,
  gapClassName = "gap-4",
  className,
}: VirtualizedGridProps<T>) {
  const columns = useResponsiveColumns(breakpoints);
  const rowCount = Math.ceil(items.length / columns);
  const parentRef = useRef<HTMLDivElement>(null);
  const [scrollElement, setScrollElement] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setScrollElement(findScrollParent(parentRef.current));
  }, []);

  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => scrollElement,
    estimateSize: () => estimatedRowHeight,
    overscan: 3,
  });

  return (
    <div ref={parentRef} style={{ position: "relative", height: rowVirtualizer.getTotalSize() }}>
      {rowVirtualizer.getVirtualItems().map((virtualRow) => {
        const start = virtualRow.index * columns;
        const rowItems = items.slice(start, start + columns);

        return (
          <div
            key={virtualRow.key}
            ref={rowVirtualizer.measureElement}
            data-index={virtualRow.index}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              transform: `translateY(${virtualRow.start}px)`,
              gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
            }}
            className={cn("grid pb-4", gapClassName, className)}
          >
            {rowItems.map((item, i) => (
              <div key={getKey(item, start + i)}>{renderItem(item, start + i)}</div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
