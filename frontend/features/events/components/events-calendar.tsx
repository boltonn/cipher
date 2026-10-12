"use client";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useEventMonths } from "@/features/events/api";
import { categoryMeta } from "@/features/events/components/event-type-meta";
import { formatChipTime } from "@/features/events/lib/format";
import type { CipherEvent } from "@/features/events/types";
import { cn } from "@/lib/utils";
import {
  addMonths,
  addYears,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  isToday,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { useMemo, useState } from "react";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MAX_CHIPS = 3;
const MONTH_LABELS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

interface EventsCalendarProps {
  monthStart: Date;
  onMonthChange: (next: Date) => void;
  events: CipherEvent[];
  onSelect: (event: CipherEvent) => void;
  isLoading?: boolean;
  /** Scopes the month/year picker's event counts. */
  datasetIds?: string[];
}

export function EventsCalendar({
  monthStart,
  onMonthChange,
  events,
  onSelect,
  isLoading,
  datasetIds,
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
        <MonthYearPicker
          monthStart={monthStart}
          onMonthChange={onMonthChange}
          datasetIds={datasetIds}
        />
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
            aria-label="Previous year"
            title="Previous year"
            onClick={() => onMonthChange(addYears(monthStart, -1))}
          >
            <ChevronsLeft size={15} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Previous month"
            title="Previous month"
            onClick={() => onMonthChange(addMonths(monthStart, -1))}
          >
            <ChevronLeft size={15} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Next month"
            title="Next month"
            onClick={() => onMonthChange(addMonths(monthStart, 1))}
          >
            <ChevronRight size={15} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Next year"
            title="Next year"
            onClick={() => onMonthChange(addYears(monthStart, 1))}
          >
            <ChevronsRight size={15} />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 border-t border-border">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="border-b border-border px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
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
                  outside
                    ? "text-muted-foreground/50"
                    : "text-muted-foreground",
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
                      <span
                        className={cn(
                          "h-1.5 w-1.5 shrink-0 rounded-full",
                          cat.dotClass
                        )}
                      />
                      <span className="truncate font-medium">{e.title}</span>
                      {e.recurrenceRule && (
                        <span className="shrink-0 opacity-60" title="Recurring">
                          ↻
                        </span>
                      )}
                      <span className="ml-auto shrink-0 opacity-60">
                        {formatChipTime(e)}
                      </span>
                    </button>
                  );
                })}
                {dayEvents.length > MAX_CHIPS && (
                  <button
                    type="button"
                    onClick={() => onSelect(dayEvents[MAX_CHIPS])}
                    className="px-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
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

/**
 * The month title as a picker: step years, click a month, or jump straight to a
 * year / the earliest / latest month that has events. Counts show where the data is.
 */
function MonthYearPicker({
  monthStart,
  onMonthChange,
  datasetIds,
}: {
  monthStart: Date;
  onMonthChange: (next: Date) => void;
  datasetIds?: string[];
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [viewYear, setViewYear] = useState(monthStart.getFullYear());
  const { data: months = [] } = useEventMonths(datasetIds);

  const { countByMonth, countByYear } = useMemo(() => {
    const byMonth = new Map<string, number>();
    const byYear = new Map<number, number>();
    for (const { month, count } of months) {
      byMonth.set(month, count);
      const year = Number(month.slice(0, 4));
      byYear.set(year, (byYear.get(year) ?? 0) + count);
    }
    return { countByMonth: byMonth, countByYear: byYear };
  }, [months]);

  const jumpTo = (date: Date) => {
    onMonthChange(startOfMonth(date));
    setIsOpen(false);
  };
  const jumpToMonthKey = (key: string) =>
    jumpTo(new Date(`${key}-01T00:00:00`));

  return (
    <Popover
      open={isOpen}
      onOpenChange={(open) => {
        if (open) setViewYear(monthStart.getFullYear());
        setIsOpen(open);
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 h-8 gap-1.5 px-2 text-sm font-semibold"
        >
          {format(monthStart, "MMMM yyyy")}
          <ChevronDown size={14} className="text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 space-y-3 p-3">
        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Previous year"
            onClick={() => setViewYear((y) => y - 1)}
          >
            <ChevronLeft size={15} />
          </Button>
          <div className="text-center">
            <p className="text-sm font-semibold text-foreground">{viewYear}</p>
            <p className="text-[11px] text-muted-foreground">
              {(countByYear.get(viewYear) ?? 0).toLocaleString()} events
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Next year"
            onClick={() => setViewYear((y) => y + 1)}
          >
            <ChevronRight size={15} />
          </Button>
        </div>

        <div className="grid grid-cols-4 gap-1">
          {MONTH_LABELS.map((label, i) => {
            const key = `${viewYear}-${String(i + 1).padStart(2, "0")}`;
            const count = countByMonth.get(key) ?? 0;
            const isCurrent =
              viewYear === monthStart.getFullYear() &&
              i === monthStart.getMonth();
            return (
              <button
                key={key}
                type="button"
                onClick={() => jumpTo(new Date(viewYear, i, 1))}
                className={cn(
                  "flex flex-col items-center rounded-md border py-1.5 text-xs transition-colors",
                  isCurrent
                    ? "border-primary bg-primary text-primary-foreground"
                    : count > 0
                      ? "border-primary/30 bg-primary/10 text-foreground hover:bg-primary/20"
                      : "border-transparent text-muted-foreground hover:bg-muted"
                )}
              >
                <span className="font-medium">{label}</span>
                <span
                  className={cn(
                    "text-[11px]",
                    !isCurrent && "text-muted-foreground"
                  )}
                >
                  {count > 0 ? count.toLocaleString() : "–"}
                </span>
              </button>
            );
          })}
        </div>

        {countByYear.size > 0 && (
          <div className="space-y-1.5 border-t border-border pt-2">
            <p className="text-[11px] font-medium text-muted-foreground">
              Years with events
            </p>
            <div className="flex max-h-24 flex-wrap gap-1 overflow-y-auto">
              {[...countByYear].map(([year, count]) => (
                <button
                  key={year}
                  type="button"
                  onClick={() => setViewYear(year)}
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                    year === viewYear
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground"
                  )}
                >
                  {year}{" "}
                  <span className="opacity-60">{count.toLocaleString()}</span>
                </button>
              ))}
            </div>
            <div className="flex gap-1 pt-1">
              <Button
                variant="outline"
                size="sm"
                className="h-7 flex-1 text-xs"
                onClick={() => jumpToMonthKey(months[0].month)}
              >
                Earliest event
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 flex-1 text-xs"
                onClick={() => jumpToMonthKey(months[months.length - 1].month)}
              >
                Latest event
              </Button>
            </div>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** Helper: [first-visible-day, last-visible-day] ISO strings for a month's grid. */
export function monthGridRange(monthStart: Date): { from: string; to: string } {
  return {
    from: startOfWeek(startOfMonth(monthStart)).toISOString(),
    to: endOfWeek(endOfMonth(monthStart)).toISOString(),
  };
}
