"use client";

import type { HistogramGranularityType, LoadHistogramBucket } from "@/features/datasets/types";
import { cn } from "@/lib/utils";
import { motion } from "motion/react";
import { useState } from "react";

interface LoadHistogramChartProps {
  buckets: LoadHistogramBucket[];
  granularity: HistogramGranularityType;
  /** dateBucket of the currently active drill-down, if any. */
  selectedBucket?: string;
  /** Click a bar to filter the rest of the page to that bucket's window; clicking it again clears it. */
  onSelectBucket?: (bucket: LoadHistogramBucket) => void;
}

const formatBucketLabel = (dateString: string, granularity: HistogramGranularityType) => {
  const date = new Date(dateString);
  if (granularity === "month") return date.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

/** Hand-rolled bar chart: hover a bar to see its exact date and count, click to drill in. */
export function LoadHistogramChart({ buckets, granularity, selectedBucket, onSelectBucket }: LoadHistogramChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (buckets.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-xs text-muted-foreground">
        No files loaded in this range
      </div>
    );
  }

  const maxCount = Math.max(...buckets.map((b) => b.count));
  const hoveredBucket = hovered != null ? buckets[hovered] : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end justify-between h-48 gap-px">
        {buckets.map((bucket, index) => {
          const heightPct = maxCount > 0 ? (bucket.count / maxCount) * 100 : 0;
          const isActive = selectedBucket === bucket.dateBucket;
          return (
            <button
              key={bucket.dateBucket}
              type="button"
              onClick={() => onSelectBucket?.(bucket)}
              className={cn(
                "flex-1 h-full flex items-end group relative",
                onSelectBucket && "cursor-pointer",
                selectedBucket && !isActive && "opacity-40"
              )}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            >
              <motion.div
                className={cn(
                  "w-full rounded-t transition-colors min-h-[2px]",
                  isActive ? "bg-primary" : "bg-primary/30 group-hover:bg-primary/60"
                )}
                animate={{ height: `${heightPct}%` }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              />
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between border-t border-border/50 pt-2">
        <span className="text-[10px] font-mono text-muted-foreground">
          {formatBucketLabel(buckets[0].dateBucket, granularity)}
        </span>
        {hoveredBucket ? (
          <span className="text-[10px] font-mono text-primary">
            {formatBucketLabel(hoveredBucket.dateBucket, granularity)} &middot; {hoveredBucket.count.toLocaleString()} files
          </span>
        ) : (
          <span className="text-[10px] font-mono text-muted-foreground">Hover a bar for details</span>
        )}
        <span className="text-[10px] font-mono text-muted-foreground">
          {formatBucketLabel(buckets[buckets.length - 1].dateBucket, granularity)}
        </span>
      </div>
    </div>
  );
}
