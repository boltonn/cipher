"use client";

import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import type { GridSelection } from "@/hooks/use-grid-selection";

interface SelectionBarProps {
  selection: GridSelection;
  /** Ids of every item currently loaded, for "Select all". */
  loadedIds: string[];
  /** "Select all" reaches past the loaded items (e.g. every similarity result): its count and loader. */
  selectAllCount?: number;
  onSelectAll?: () => void;
  isSelectingAll?: boolean;
  /** The bulk actions for the current selection. */
  children: React.ReactNode;
}

/** Floating bulk-action bar for a card grid; renders nothing until something is selected. */
export function SelectionBar({
  selection,
  loadedIds,
  selectAllCount = loadedIds.length,
  onSelectAll = () => selection.selectAll(loadedIds),
  isSelectingAll,
  children,
}: SelectionBarProps) {
  const count = selection.selectedIds.size;
  if (count === 0) return null;

  return (
    <div className="sticky bottom-4 z-20 mx-auto flex w-fit items-center gap-2 rounded-full border border-border bg-popover px-3 py-1.5 shadow-lg">
      <span className="text-[11px] text-muted-foreground tabular-nums">
        {count.toLocaleString()} selected
      </span>
      {count < selectAllCount && (
        <Button
          size="sm"
          variant="ghost"
          className="h-7 gap-1 px-2 text-[11px] text-muted-foreground"
          disabled={isSelectingAll}
          onClick={onSelectAll}
        >
          {isSelectingAll && <Loader2 size={12} className="animate-spin" />}
          Select all {selectAllCount.toLocaleString()}
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
