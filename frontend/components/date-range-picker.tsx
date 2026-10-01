"use client";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { CalendarIcon, ChevronDownIcon, X } from "lucide-react";
import { useState } from "react";
import type { DateRange } from "react-day-picker";

export interface DateRangeValue {
  from?: string;
  to?: string;
}

interface DateRangePickerProps {
  value: DateRangeValue;
  onChange: (value: DateRangeValue) => void;
  placeholder?: string;
  /** Sizes the whole control (height + width), like any other trigger -- default `h-8`. */
  className?: string;
}

/** Date-range picker: pick a from/to pair via a single calendar in range mode. */
export function DateRangePicker({
  value,
  onChange,
  placeholder = "Pick a date range",
  className,
}: DateRangePickerProps) {
  const [open, setOpen] = useState(false);

  const selected: DateRange | undefined = value.from
    ? { from: new Date(value.from), to: value.to ? new Date(value.to) : undefined }
    : undefined;

  const label = selected?.from
    ? selected.to
      ? `${format(selected.from, "MMM d, yyyy")} - ${format(selected.to, "MMM d, yyyy")}`
      : format(selected.from, "MMM d, yyyy")
    : placeholder;

  return (
    <div className={cn("relative h-8", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className={cn(
              "h-full w-full justify-start gap-1.5 rounded-md pl-2.5 pr-2 text-left font-normal text-xs bg-muted/40 border-border hover:bg-muted/60",
              selected?.from && "pr-8",
              !selected?.from && "text-muted-foreground"
            )}
          >
            <CalendarIcon className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="flex-1 truncate">{label}</span>
            {!selected?.from && (
              <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0 bg-popover border-border" align="start">
          <Calendar
            mode="range"
            captionLayout="dropdown"
            numberOfMonths={2}
            selected={selected}
            onSelect={(range) => {
              onChange({ from: range?.from?.toISOString(), to: range?.to?.toISOString() });
              if (range?.from && range?.to) setOpen(false);
            }}
            className="rounded-md border-none"
          />
        </PopoverContent>
      </Popover>
      {selected?.from && (
        // Rendered as a sibling, not a child of the trigger Button, since a <button>
        // cannot nest inside another <button> without breaking HTML validity/hydration.
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onChange({ from: undefined, to: undefined });
          }}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          aria-label="Clear date range"
        >
          <X size={12} />
        </button>
      )}
    </div>
  );
}
