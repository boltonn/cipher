"use client";

import type { FiletypeBreakdownItem } from "@/features/datasets/types";

interface FiletypeBreakdownListProps {
  items: FiletypeBreakdownItem[];
}

/** Horizontal bar list: each row's fill width is proportional to its share of the total. */
export function FiletypeBreakdownList({ items }: FiletypeBreakdownListProps) {
  if (items.length === 0) {
    return <div className="flex items-center justify-center h-24 text-xs text-slate-600">No files in this range</div>;
  }

  const total = items.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => {
        const pct = total > 0 ? (item.count / total) * 100 : 0;
        return (
          <div key={item.filetype} className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-mono text-slate-300 uppercase">{item.filetype}</span>
              <span className="text-slate-500">
                {item.count.toLocaleString()} <span className="text-slate-600">({pct.toFixed(0)}%)</span>
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div className="h-full rounded-full bg-indigo-500/50" style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
