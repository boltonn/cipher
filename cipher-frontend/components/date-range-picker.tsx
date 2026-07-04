"use client";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { CalendarIcon, X } from "lucide-react";
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
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className={cn(
            "w-full justify-start text-left font-normal text-xs h-9 bg-slate-900/40 border-white/10 hover:bg-slate-900/60",
            !selected?.from && "text-slate-500",
            className
          )}
        >
          <CalendarIcon className="mr-2 h-3 w-3 shrink-0" />
          <span className="truncate">{label}</span>
          {selected?.from && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ from: undefined, to: undefined });
              }}
              className="ml-auto text-slate-500 hover:text-white"
              aria-label="Clear date range"
            >
              <X size={12} />
            </button>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0 bg-slate-950 border-white/10" align="start">
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
  );
}
