"use client";

import { cn } from "@/lib/utils";
import { format } from "date-fns";
import type Graph from "graphology";
import { CalendarRange, X } from "lucide-react";
import { useRef, useState } from "react";

const BIN_COUNT = 72;
const MAX_TICKS = 8;
const DAY = 86_400_000;

interface DateRange {
  dateFrom: string | undefined;
  dateTo: string | undefined;
}

interface GraphTimeBarProps {
  graph: Graph;
  dateFrom: string | undefined;
  dateTo: string | undefined;
  onChange: (range: DateRange) => void;
  onClose: () => void;
}

interface Drag {
  mode: "new" | "move" | "from" | "to";
  anchor: number;
  from: number;
  to: number;
}

/**
 * Brushable histogram of when the canvas' relationships were active. Each edge
 * is a first-seen..last-seen span, so a bar counts the relationships active in
 * that slice -- not individual emails. Drag to select a window, drag the window
 * or its edges to adjust, click outside it to clear.
 */
export function GraphTimeBar({
  graph,
  dateFrom,
  dateTo,
  onChange,
  onClose,
}: GraphTimeBarProps) {
  const plotRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const [hoverBin, setHoverBin] = useState<number | null>(null);

  const spans: [number, number][] = [];
  let undated = 0;
  graph.forEachEdge((_e, attrs) => {
    const start = attrs.dateStart as number | null;
    if (start == null) undated += 1;
    else spans.push([start, (attrs.dateEnd as number | null) ?? start]);
  });

  if (spans.length === 0) {
    return (
      <Shell onClose={onClose}>
        <p className="py-3 text-center text-xs text-muted-foreground">
          No dated relationships on the canvas yet — only emails and events carry
          dates.
        </p>
      </Shell>
    );
  }

  const min = Math.min(...spans.map(([s]) => s));
  const max = Math.max(Math.max(...spans.map(([, e]) => e)), min + DAY);
  const binWidth = (max - min) / BIN_COUNT;
  const bins = Array.from({ length: BIN_COUNT }, (_, i) => {
    const lo = min + i * binWidth;
    const hi = lo + binWidth;
    return spans.filter(([s, e]) => e >= lo && s < hi).length;
  });
  const peak = Math.max(...bins, 1);

  const selFrom = dateFrom ? Date.parse(dateFrom) : null;
  const selTo = dateTo ? Date.parse(dateTo) : null;
  const hasSelection = selFrom != null || selTo != null;
  const from = Math.max(selFrom ?? min, min);
  const to = Math.min(selTo ?? max, max);
  const pct = (ms: number) => ((ms - min) / (max - min)) * 100;
  const inSelection = spans.filter(([s, e]) => e >= from && s <= to).length;

  const commit = (a: number, b: number) =>
    onChange({
      dateFrom: new Date(Math.max(min, Math.min(a, b))).toISOString(),
      dateTo: new Date(Math.min(max, Math.max(a, b))).toISOString(),
    });
  const clear = () => onChange({ dateFrom: undefined, dateTo: undefined });

  const msAt = (clientX: number) => {
    const rect = plotRef.current?.getBoundingClientRect();
    if (!rect) return min;
    const t = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return min + t * (max - min);
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const handle = (e.target as HTMLElement).dataset.handle as "from" | "to" | undefined;
    const at = msAt(e.clientX);
    const mode = handle ?? (hasSelection && at >= from && at <= to ? "move" : "new");
    dragRef.current = { mode, anchor: at, from, to };
    setHoverBin(null);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const at = msAt(e.clientX);
    const drag = dragRef.current;
    if (!drag) {
      setHoverBin(Math.min(BIN_COUNT - 1, Math.floor((at - min) / binWidth)));
      return;
    }
    if (drag.mode === "new") commit(drag.anchor, at);
    else if (drag.mode === "from") commit(at, drag.to);
    else if (drag.mode === "to") commit(drag.from, at);
    else {
      const delta = Math.min(max - drag.to, Math.max(min - drag.from, at - drag.anchor));
      commit(drag.from + delta, drag.to + delta);
    }
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    // a click (no real drag) outside the window clears it
    if (drag?.mode === "new" && Math.abs(msAt(e.clientX) - drag.anchor) < binWidth / 4) {
      clear();
    }
  };
  const nudge = (side: "from" | "to") => (e: React.KeyboardEvent) => {
    const step = e.key === "ArrowLeft" ? -binWidth : e.key === "ArrowRight" ? binWidth : 0;
    if (!step) return;
    e.preventDefault();
    if (side === "from") commit(from + step, to);
    else commit(from, to + step);
  };

  const fmt = (ms: number) => format(ms, "MMM d, yyyy");
  const readout =
    hoverBin != null
      ? `${format(min + hoverBin * binWidth, "MMM yyyy")} · ${bins[hoverBin].toLocaleString()} active`
      : hasSelection
        ? `${fmt(from)} – ${fmt(to)} · ${inSelection.toLocaleString()} of ${spans.length.toLocaleString()} dated relationships`
        : `${fmt(min)} – ${fmt(max)} · ${spans.length.toLocaleString()} dated relationships`;

  return (
    <Shell onClose={onClose}>
      <div className="flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
        <span className="font-mono text-foreground">{readout}</span>
        {undated > 0 && <span>· {undated.toLocaleString()} undated always shown</span>}
        {hasSelection ? (
          <button
            type="button"
            onClick={clear}
            className="ml-auto text-primary hover:underline"
          >
            Clear window
          </button>
        ) : (
          <span className="ml-auto">Drag across the bars to pick a window</span>
        )}
      </div>

      <div
        ref={plotRef}
        role="group"
        aria-label="Relationships active over time; drag to select a window"
        className="relative mt-1.5 h-14 cursor-crosshair touch-none select-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => setHoverBin(null)}
      >
        <div className="flex h-full items-end gap-px border-b border-border">
          {bins.map((count, i) => {
            const mid = min + (i + 0.5) * binWidth;
            return (
              <div
                key={i}
                className={cn(
                  "min-h-px flex-1 rounded-t-sm",
                  !hasSelection || (mid >= from && mid <= to)
                    ? "bg-primary"
                    : "bg-muted-foreground/25",
                  hoverBin === i && "opacity-70"
                )}
                style={{ height: `${(count / peak) * 100}%` }}
              />
            );
          })}
        </div>
        <span className="pointer-events-none absolute left-0 top-0 font-mono text-[11px] text-muted-foreground">
          {peak.toLocaleString()}
        </span>

        {hasSelection && (
          <div
            className="absolute inset-y-0 cursor-grab border-x border-primary bg-primary/10"
            style={{ left: `${pct(from)}%`, width: `${pct(to) - pct(from)}%` }}
          >
            {(["from", "to"] as const).map((side) => (
              <button
                key={side}
                type="button"
                data-handle={side}
                role="slider"
                aria-label={side === "from" ? "Window start" : "Window end"}
                aria-valuemin={min}
                aria-valuemax={max}
                aria-valuenow={side === "from" ? from : to}
                aria-valuetext={fmt(side === "from" ? from : to)}
                onKeyDown={nudge(side)}
                className={cn(
                  "absolute inset-y-0 w-3 cursor-ew-resize rounded-sm focus-visible:outline-2 focus-visible:outline-primary",
                  side === "from" ? "-left-1.5" : "-right-1.5"
                )}
              />
            ))}
          </div>
        )}
      </div>

      <div className="relative mt-1 h-4">
        {ticks(min, max).map((tick) => (
          <span
            key={tick.ms}
            className="absolute -translate-x-1/2 font-mono text-[11px] text-muted-foreground"
            style={{ left: `${pct(tick.ms)}%` }}
          >
            {tick.label}
          </span>
        ))}
      </div>
    </Shell>
  );
}

/** Year ticks for multi-year domains, month ticks under two years; at most MAX_TICKS. */
function ticks(min: number, max: number): { ms: number; label: string }[] {
  const first = new Date(min);
  const months =
    (new Date(max).getFullYear() - first.getFullYear()) * 12 +
    new Date(max).getMonth() -
    first.getMonth();
  const byYear = months >= 24;
  const step = Math.max(1, Math.ceil((byYear ? months / 12 : months) / MAX_TICKS));
  const out: { ms: number; label: string }[] = [];
  for (let i = 1; out.length < MAX_TICKS + 1; i += step) {
    const d = byYear
      ? new Date(first.getFullYear() + i, 0, 1)
      : new Date(first.getFullYear(), first.getMonth() + i, 1);
    if (d.getTime() > max) break;
    out.push({ ms: d.getTime(), label: format(d, byYear ? "yyyy" : "MMM yyyy") });
  }
  return out;
}

function Shell({
  onClose,
  children,
}: {
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-2 shrink-0 rounded-xl border border-border bg-muted/30 p-2">
      <div className="flex items-center justify-between px-1 pb-1">
        <span className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
          <CalendarRange size={11} />
          Timeline · relationships active
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Hide timeline"
          className="text-muted-foreground hover:text-foreground"
        >
          <X size={13} />
        </button>
      </div>
      {children}
    </div>
  );
}
