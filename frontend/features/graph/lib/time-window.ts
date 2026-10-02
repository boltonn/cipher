/** Inclusive epoch-ms bounds; a null side is open. */
export interface TimeWindow {
  from: number | null;
  to: number | null;
}

export function toTimeWindow(dateFrom?: string, dateTo?: string): TimeWindow | null {
  if (!dateFrom && !dateTo) return null;
  return {
    from: dateFrom ? Date.parse(dateFrom) : null,
    to: dateTo ? Date.parse(dateTo) : null,
  };
}

/**
 * Whether an edge's observed span (`dateStart`..`dateEnd`, set in `buildNetwork`)
 * overlaps the window. Undated edges (family, selectors) always pass -- the
 * window can only say "active somewhere in this period", not count within it.
 */
export function edgeInWindow(
  attrs: Record<string, unknown>,
  window: TimeWindow
): boolean {
  const start = attrs.dateStart as number | null | undefined;
  if (start == null) return true;
  const end = (attrs.dateEnd as number | null | undefined) ?? start;
  return (
    (window.from == null || end >= window.from) &&
    (window.to == null || start <= window.to)
  );
}
