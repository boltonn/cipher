"use client";

import type { HistogramGranularityType, LoadHistogramBucket } from "@/features/datasets/types";
import { useState } from "react";

interface LoadHistogramChartProps {
  buckets: LoadHistogramBucket[];
  granularity: HistogramGranularityType;
}

const formatBucketLabel = (dateString: string, granularity: HistogramGranularityType) => {
  const date = new Date(dateString);
  if (granularity === "month") return date.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

/** Hand-rolled bar chart: hover a bar to see its exact date and count. */
export function LoadHistogramChart({ buckets, granularity }: LoadHistogramChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (buckets.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-xs text-slate-600">
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
          return (
            <div
              key={bucket.dateBucket}
              className="flex-1 h-full flex items-end group relative"
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            >
              <div
                className="w-full rounded-t bg-indigo-500/30 group-hover:bg-indigo-500/60 transition-colors min-h-[2px]"
                style={{ height: `${heightPct}%` }}
              />
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between border-t border-white/5 pt-2">
        <span className="text-[10px] font-mono text-slate-500">
          {formatBucketLabel(buckets[0].dateBucket, granularity)}
        </span>
        {hoveredBucket ? (
          <span className="text-[10px] font-mono text-indigo-400">
            {formatBucketLabel(hoveredBucket.dateBucket, granularity)} &middot; {hoveredBucket.count.toLocaleString()} files
          </span>
        ) : (
          <span className="text-[10px] font-mono text-slate-600">Hover a bar for details</span>
        )}
        <span className="text-[10px] font-mono text-slate-500">
          {formatBucketLabel(buckets[buckets.length - 1].dateBucket, granularity)}
        </span>
      </div>
    </div>
  );
}
