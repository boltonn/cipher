"use client";

import { Button } from "@/components/ui/button";
import { categoryMeta } from "@/features/events/components/event-type-meta";
import { formatChipTime } from "@/features/events/lib/format";
import type { CipherEvent } from "@/features/events/types";
import { cn } from "@/lib/utils";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  isToday,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo } from "react";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MAX_CHIPS = 3;

interface EventsCalendarProps {
  monthStart: Date;
  onMonthChange: (next: Date) => void;
  events: CipherEvent[];
  onSelect: (event: CipherEvent) => void;
  isLoading?: boolean;
}

export function EventsCalendar({
  monthStart,
  onMonthChange,
  events,
  onSelect,
  isLoading,
}: EventsCalendarProps) {
  const days = useMemo(() => {
    const gridStart = startOfWeek(startOfMonth(monthStart));
    const gridEnd = endOfWeek(endOfMonth(monthStart));
    return eachDayOfInterval({ start: gridStart, end: gridEnd });
  }, [monthStart]);

  const byDay = useMemo(() => {
    const map = new Map<string, CipherEvent[]>();
    for (const e of events) {
      const key = format(new Date(e.dateStart), "yyyy-MM-dd");
      const bucket = map.get(key);
      if (bucket) bucket.push(e);
      else map.set(key, [e]);
    }
    for (const bucket of map.values()) {
      bucket.sort((a, b) => +new Date(a.dateStart) - +new Date(b.dateStart));
    }
    return map;
  }, [events]);

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card/40 transition-opacity",
        isLoading && "opacity-60"
      )}
    >
      <div className="flex items-center justify-between px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground">
          {format(monthStart, "MMMM yyyy")}
        </h3>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => onMonthChange(startOfMonth(new Date()))}
          >
            Today
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Previous month"
            onClick={() => onMonthChange(addMonths(monthStart, -1))}
          >
            <ChevronLeft size={15} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Next month"
            onClick={() => onMonthChange(addMonths(monthStart, 1))}
          >
            <ChevronRight size={15} />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 border-t border-border">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="border-b border-border px-2 py-1.5 text-[10px] font-black uppercase tracking-widest text-muted-foreground"
          >
            {d}
          </div>
        ))}
        {days.map((day) => {
          const key = format(day, "yyyy-MM-dd");
          const dayEvents = byDay.get(key) ?? [];
          const outside = !isSameMonth(day, monthStart);
          return (
            <div
              key={key}
              className={cn(
                "min-h-24 border-b border-r border-border p-1.5 [&:nth-child(7n+1)]:border-l-0",
                outside && "bg-muted/20"
              )}
            >
              <div
                className={cn(
                  "mb-1 flex h-5 w-5 items-center justify-center rounded-full text-[11px]",
                  outside ? "text-muted-foreground/50" : "text-muted-foreground",
                  isToday(day) && "bg-primary font-bold text-primary-foreground"
                )}
              >
                {format(day, "d")}
              </div>
              <div className="space-y-0.5">
                {dayEvents.slice(0, MAX_CHIPS).map((e) => {
                  const cat = categoryMeta(e.category);
                  return (
                    <button
                      key={e.id}
                      type="button"
                      onClick={() => onSelect(e)}
                      title={e.title}
                      className={cn(
                        "flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-[11px] transition-colors hover:brightness-125",
                        cat.bgClass,
                        cat.textClass,
                        e.status === "cancelled" && "line-through opacity-60"
                      )}
                    >
                      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", cat.dotClass)} />
                      <span className="truncate font-medium">{e.title}</span>
                      {e.recurrenceRule && (
                        <span className="shrink-0 opacity-60" title="Recurring">
                          ↻
                        </span>
                      )}
                      <span className="ml-auto shrink-0 opacity-60">{formatChipTime(e)}</span>
                    </button>
                  );
                })}
                {dayEvents.length > MAX_CHIPS && (
                  <button
                    type="button"
                    onClick={() => onSelect(dayEvents[MAX_CHIPS])}
                    className="px-1 text-[10px] font-medium text-muted-foreground hover:text-foreground"
                  >
                    +{dayEvents.length - MAX_CHIPS} more
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {!isLoading && events.length === 0 && (
        <p className="px-4 py-6 text-center text-xs italic text-muted-foreground">
          No events in {format(monthStart, "MMMM")}.
        </p>
      )}
    </div>
  );
}

/** Helper: [first-visible-day, last-visible-day] ISO strings for a month's grid. */
export function monthGridRange(monthStart: Date): { from: string; to: string } {
  return {
    from: startOfWeek(startOfMonth(monthStart)).toISOString(),
    to: endOfWeek(endOfMonth(monthStart)).toISOString(),
  };
}
