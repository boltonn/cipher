"use client";

import type { FiletypeBreakdownItem } from "@/features/datasets/types";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";

interface FiletypeBreakdownListProps {
  items: FiletypeBreakdownItem[];
  /** Currently active drill-down value, if any. */
  selected?: string;
  /** Click a row to filter the rest of the page by it; clicking the active row again clears it. */
  onSelect?: (filetype: string | undefined) => void;
}

/** Horizontal bar list: each row's fill width is proportional to its share of the total. */
export function FiletypeBreakdownList({
  items,
  selected,
  onSelect,
}: FiletypeBreakdownListProps) {
  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center h-80 text-xs text-muted-foreground">
        No files in this range
      </div>
    );
  }

  const total = items.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="flex flex-col gap-3 h-80 overflow-y-auto pr-1">
      {items.map((item) => {
        const pct = total > 0 ? (item.count / total) * 100 : 0;
        const isActive = selected === item.filetype;
        return (
          <motion.button
            key={item.filetype}
            layout
            type="button"
            onClick={() => onSelect?.(isActive ? undefined : item.filetype)}
            transition={{ duration: 0.2 }}
            className={cn(
              "flex flex-col gap-1 text-left rounded-lg -mx-1 px-1 py-0.5 transition-opacity",
              onSelect && "cursor-pointer hover:opacity-100",
              selected && !isActive && "opacity-40"
            )}
          >
            <div className="flex items-center justify-between text-xs">
              <span
                className={cn(
                  "font-mono uppercase",
                  isActive ? "text-primary" : "text-foreground"
                )}
              >
                {item.filetype}
              </span>
              <span className="text-muted-foreground">
                {item.count.toLocaleString()}{" "}
                <span className="text-muted-foreground">({pct.toFixed(0)}%)</span>
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
              <motion.div
                className={cn(
                  "h-full rounded-full",
                  isActive ? "bg-primary" : "bg-primary/50"
                )}
                animate={{ width: `${pct}%` }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              />
            </div>
          </motion.button>
        );
      })}
    </div>
  );
}
