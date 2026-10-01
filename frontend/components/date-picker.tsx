"use client";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { format, isValid, parse } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { useState } from "react";

interface DatePickerProps {
  /** ISO date string */
  value?: string;
  onChange: (isoDate: string | undefined) => void;
  placeholder?: string;
  className?: string;
}

const formatValue = (value?: string) => (value ? format(new Date(value), "MM/dd/yyyy") : "");

/**
 * Fast date picker: type a date directly (MM/DD/YYYY) or use the calendar,
 * which has dropdown month/year navigation (react-day-picker's
 * captionLayout="dropdown") so jumping to e.g. a birth year decades back is
 * two clicks instead of scrolling one month at a time.
 */
export function DatePicker({ value, onChange, placeholder = "Pick a date", className }: DatePickerProps) {
  const [open, setOpen] = useState(false);
  const [inputValue, setInputValue] = useState(formatValue(value));

  // Re-sync the typable text from an external value change (not from typing) --
  // adjusting state during render, per React's documented pattern, avoids the
  // extra render pass a useEffect-based sync would cost.
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    setInputValue(formatValue(value));
  }

  const commitTypedDate = () => {
    const trimmed = inputValue.trim();
    if (!trimmed) {
      onChange(undefined);
      return;
    }
    const parsed = parse(trimmed, "MM/dd/yyyy", new Date());
    if (isValid(parsed)) {
      onChange(parsed.toISOString());
    } else {
      setInputValue(formatValue(value));
    }
  };

  return (
    <div className={cn("relative h-9", className)}>
      <Input
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onBlur={commitTypedDate}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commitTypedDate();
          }
        }}
        placeholder="MM/DD/YYYY"
        className="h-full pr-9 bg-muted/40 border-border text-sm"
      />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute right-0 top-0 aspect-square h-full w-auto text-muted-foreground hover:text-foreground"
            aria-label={placeholder}
          >
            <CalendarIcon size={14} />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0 bg-popover border-border" align="end">
          <Calendar
            mode="single"
            captionLayout="dropdown"
            selected={value ? new Date(value) : undefined}
            onSelect={(d) => {
              onChange(d?.toISOString());
              setOpen(false);
            }}
            className="rounded-md border-none"
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
