"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export interface FaceSelection {
  selectedIds: Set<string>;
  /** Toggle one face; `range` (shift-click) selects everything between it and the last toggled face. */
  toggle: (id: string, orderedIds: string[], range: boolean) => void;
  selectAll: (ids: string[]) => void;
  clear: () => void;
}

/** Multi-select over a face grid. Escape clears. Callbacks are stable so memoized cards don't re-render. */
export function useFaceSelection(): FaceSelection {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const anchorRef = useRef<string | null>(null);

  const toggle = useCallback(
    (id: string, orderedIds: string[], range: boolean) => {
      const anchorIndex = anchorRef.current
        ? orderedIds.indexOf(anchorRef.current)
        : -1;
      const index = orderedIds.indexOf(id);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (range && anchorIndex >= 0 && index >= 0) {
          const [start, end] =
            anchorIndex < index ? [anchorIndex, index] : [index, anchorIndex];
          for (const rangeId of orderedIds.slice(start, end + 1))
            next.add(rangeId);
        } else if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return next;
      });
      anchorRef.current = id;
    },
    []
  );

  const selectAll = useCallback(
    (ids: string[]) => setSelectedIds(new Set(ids)),
    []
  );
  const clear = useCallback(() => {
    anchorRef.current = null;
    setSelectedIds(new Set());
  }, []);

  const hasSelection = selectedIds.size > 0;
  useEffect(() => {
    if (!hasSelection) return;
    const onKeyDown = (e: KeyboardEvent) => e.key === "Escape" && clear();
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasSelection, clear]);

  return { selectedIds, toggle, selectAll, clear };
}
