"use client";

import { cn } from "@/lib/utils";
import { useState } from "react";
import type { MonthCount } from "../types";

const MAX_BARS = 48;

export interface TimeBin {
  label: string;
  /** Inclusive first day, `YYYY-MM-DD`. */
  dateFrom: string;
  /** Inclusive last day, `YYYY-MM-DD`. */
  dateTo: string;
  files: number;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function lastDay(year: number, month: number) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function pad(n: number) {
  return String(n).padStart(2, "0");
}

/** Month counts -> contiguous bins (months, quarters or years) so a long span stays ≤ `MAX_BARS` bars. */
export function binMonths(months: MonthCount[]): TimeBin[] {
  if (months.length === 0) return [];
  const counts = new Map(months.map((m) => [m.month, m.files]));
  const [firstYear, firstMonth] = months[0].month.split("-").map(Number);
  const [lastYear, lastMonth] = months[months.length - 1].month.split("-").map(Number);
  const span = (lastYear - firstYear) * 12 + (lastMonth - firstMonth) + 1;
  const size = span <= MAX_BARS ? 1 : span <= MAX_BARS * 3 ? 3 : 12;
  const startMonth = size === 12 ? 1 : size === 3 ? Math.floor((firstMonth - 1) / 3) * 3 + 1 : firstMonth;
  const bins: TimeBin[] = [];
  for (let year = firstYear, month = startMonth; year < lastYear || (year === lastYear && month <= lastMonth); ) {
    let files = 0;
    for (let i = 0; i < size; i++) {
      const y = year + Math.floor((month - 1 + i) / 12);
      const m = ((month - 1 + i) % 12) + 1;
      files += counts.get(`${y}-${pad(m)}`) ?? 0;
    }
    const endMonthIndex = month - 1 + size - 1;
    const endYear = year + Math.floor(endMonthIndex / 12);
    const endMonth = (endMonthIndex % 12) + 1;
    const label =
      size === 12 ? `${year}` : size === 3 ? `Q${Math.ceil(month / 3)} ${year}` : `${MONTHS[month - 1]} ${year}`;
    bins.push({
      label,
      dateFrom: `${year}-${pad(month)}-01`,
      dateTo: `${endYear}-${pad(endMonth)}-${pad(lastDay(endYear, endMonth))}`,
      files,
    });
    month += size;
    year += Math.floor((month - 1) / 12);
    month = ((month - 1) % 12) + 1;
  }
  return bins;
}

interface TimeHistogramProps {
  months: MonthCount[];
  /** Click a bar to filter to its date range. */
  onSelect?: (bin: TimeBin) => void;
  className?: string;
  /** Plot height in px. */
  height?: number;
}

/** Files over time by content date: one hue, thin bars, value-first hover readout. */
export function TimeHistogram({ months, onSelect, className, height = 64 }: TimeHistogramProps) {
  const bins = binMonths(months);
  const [active, setActive] = useState<TimeBin | null>(null);
  if (bins.length === 0) return null;
  const peak = Math.max(...bins.map((bin) => bin.files), 1);

  return (
    <div className={cn("w-full", className)}>
      <div className="mb-1 flex h-4 items-baseline justify-between text-xs text-muted-foreground">
        {active ? (
          <span>
            <span className="font-medium text-foreground">{active.files.toLocaleString()}</span> files ·{" "}
            {active.label}
          </span>
        ) : (
          <span>Peak {peak.toLocaleString()} files</span>
        )}
      </div>
      <div className="flex items-end gap-0.5" style={{ height }} onPointerLeave={() => setActive(null)}>
        {bins.map((bin) => (
          <button
            key={bin.dateFrom}
            type="button"
            aria-disabled={!onSelect || bin.files === 0}
            aria-label={`${bin.files.toLocaleString()} files, ${bin.label}`}
            onPointerEnter={() => setActive(bin)}
            onFocus={() => setActive(bin)}
            onBlur={() => setActive(null)}
            onClick={() => bin.files > 0 && onSelect?.(bin)}
            className={cn(
              "group flex h-full min-w-0 max-w-6 flex-1 items-end outline-none",
              (!onSelect || bin.files === 0) && "cursor-default"
            )}
          >
            <span
              className={cn(
                "w-full rounded-t-[4px] bg-primary/70 transition-colors",
                "group-hover:bg-primary group-focus-visible:bg-primary",
                bin.files === 0 && "bg-transparent"
              )}
              style={{ height: bin.files ? `${Math.max(2, (bin.files / peak) * 100)}%` : 0 }}
            />
          </button>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted-foreground">
        <span>{bins[0].label}</span>
        <span>{bins[bins.length - 1].label}</span>
      </div>
    </div>
  );
}
