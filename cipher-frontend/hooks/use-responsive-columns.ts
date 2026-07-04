"use client";
import { useEffect, useState } from "react";

export interface ColumnBreakpoint {
  minWidth: number;
  columns: number;
}

/** Tailwind's default breakpoints, for matching an existing `grid-cols-N sm:... lg:...` className. */
export const TAILWIND_BREAKPOINTS = { sm: 640, md: 768, lg: 1024, xl: 1280, "2xl": 1536 };

function computeColumns(width: number, breakpoints: ColumnBreakpoint[]): number {
  const sorted = [...breakpoints].sort((a, b) => b.minWidth - a.minWidth);
  const match = sorted.find((bp) => width >= bp.minWidth);
  return match?.columns ?? sorted[sorted.length - 1]?.columns ?? 1;
}

/**
 * Mirrors a responsive `grid-cols-*` Tailwind className as a plain number,
 * for grids that need an actual column count in JS (e.g. row-based virtualization).
 */
export function useResponsiveColumns(breakpoints: ColumnBreakpoint[]): number {
  const [columns, setColumns] = useState(() =>
    typeof window === "undefined" ? breakpoints[0]?.columns ?? 1 : computeColumns(window.innerWidth, breakpoints)
  );

  useEffect(() => {
    const onResize = () => setColumns(computeColumns(window.innerWidth, breakpoints));
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- breakpoints is expected to be a stable literal at each call site
  }, [JSON.stringify(breakpoints)]);

  return columns;
}
