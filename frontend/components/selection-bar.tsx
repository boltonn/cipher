"use client";

import { Button } from "@/components/ui/button";
import type { GridSelection } from "@/hooks/use-grid-selection";

interface SelectionBarProps {
  selection: GridSelection;
  /** Ids of every item currently loaded, for "Select all". */
  loadedIds: string[];
  /** The bulk actions for the current selection. */
  children: React.ReactNode;
}

/** Floating bulk-action bar for a card grid; renders nothing until something is selected. */
export function SelectionBar({
  selection,
  loadedIds,
  children,
}: SelectionBarProps) {
  const count = selection.selectedIds.size;
  if (count === 0) return null;

  return (
    <div className="sticky bottom-4 z-20 mx-auto flex w-fit items-center gap-2 rounded-full border border-border bg-popover px-3 py-1.5 shadow-lg">
      <span className="text-[11px] text-muted-foreground tabular-nums">
        {count.toLocaleString()} selected
      </span>
      {count < loadedIds.length && (
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-[11px] text-muted-foreground"
          onClick={() => selection.selectAll(loadedIds)}
        >
          Select all {loadedIds.length.toLocaleString()}
        </Button>
      )}
      {children}
      <Button
        size="sm"
        variant="ghost"
        className="h-7 px-2 text-[11px] text-muted-foreground"
        onClick={selection.clear}
      >
        Clear
      </Button>
    </div>
  );
}
