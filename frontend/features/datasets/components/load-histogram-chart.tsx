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
  const totalCount = buckets.reduce((sum, b) => sum + b.count, 0);
  const hoveredBucket = hovered != null ? buckets[hovered] : null;

  // One bucket isn't a trend -- a single full-width slab reads as a broken
  // render, not a chart. Show the figure plainly and say why there's no shape.
  if (buckets.length === 1) {
    return (
      <div className="flex h-48 flex-col items-center justify-center gap-1.5 text-center">
        <span className="font-mono text-2xl text-foreground">
          {buckets[0].count.toLocaleString()}
        </span>
        <span className="text-[11px] text-muted-foreground">
          files on {formatBucketLabel(buckets[0].dateBucket, granularity)}
        </span>
        <span className="mt-1 text-[11px] text-muted-foreground/70">
          Widen the range or switch granularity to see load over time.
        </span>
      </div>
    );
  }

  // A handful of buckets shouldn't stretch into fat slabs; keep bars a
  // readable width and let the plot area breathe.
  const tightBars = buckets.length <= 6;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        {/* y-axis: just the max, so a bar's height maps to a real number */}
        <div className="flex w-8 shrink-0 flex-col justify-between py-0 text-right font-mono text-[11px] text-muted-foreground/60">
          <span>{maxCount.toLocaleString()}</span>
          <span>0</span>
        </div>
        <div
          className={cn(
            "relative flex h-48 flex-1 items-end gap-px",
            tightBars ? "justify-start" : "justify-between"
          )}
        >
          {/* faint mid gridline */}
          <div className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-dashed border-border/40" />
          {buckets.map((bucket, index) => {
            const heightPct = maxCount > 0 ? (bucket.count / maxCount) * 100 : 0;
            const isActive = selectedBucket === bucket.dateBucket;
            return (
              <button
                key={bucket.dateBucket}
                type="button"
                onClick={() => onSelectBucket?.(bucket)}
                className={cn(
                  "group relative flex h-full items-end",
                  tightBars ? "w-10" : "flex-1",
                  onSelectBucket && "cursor-pointer",
                  selectedBucket && !isActive && "opacity-40"
                )}
                onMouseEnter={() => setHovered(index)}
                onMouseLeave={() => setHovered(null)}
              >
                <motion.div
                  className={cn(
                    "w-full rounded-t transition-colors min-h-[2px]",
                    isActive
                      ? "bg-primary"
                      : "bg-primary/30 group-hover:bg-primary/60"
                  )}
                  animate={{ height: `${heightPct}%` }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                />
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border/50 pt-2 pl-10">
        <span className="text-[11px] font-mono text-muted-foreground">
          {formatBucketLabel(buckets[0].dateBucket, granularity)}
        </span>
        {hoveredBucket ? (
          <span className="text-[11px] font-mono text-primary">
            {formatBucketLabel(hoveredBucket.dateBucket, granularity)} &middot; {hoveredBucket.count.toLocaleString()} files
          </span>
        ) : (
          <span className="text-[11px] font-mono text-muted-foreground">
            {totalCount.toLocaleString()} files · hover a bar for details
          </span>
        )}
        <span className="text-[11px] font-mono text-muted-foreground">
          {formatBucketLabel(buckets[buckets.length - 1].dateBucket, granularity)}
        </span>
      </div>
    </div>
  );
}
