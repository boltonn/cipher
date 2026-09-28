"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import {
  Autocomplete,
  AutocompleteContent,
  AutocompleteInput,
  AutocompleteItem,
} from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useEventCategoryOptions } from "@/features/events/api";
import { EVENT_TYPE_META } from "@/features/events/components/event-type-meta";
import { EVENT_STATUSES, EVENT_TYPES, type EventFilters } from "@/features/events/types";
import { Tag, X } from "lucide-react";
import { useState } from "react";

const ALL = "__all__";

interface EventFiltersBarProps {
  value: EventFilters;
  onChange: (next: EventFilters) => void;
  queryActive?: boolean;
  onClear: () => void;
  datasetId?: string;
  /** The calendar drives its own date window via month nav, so hide the range picker there. */
  showDateRange?: boolean;
}

export function EventFiltersBar({
  value,
  onChange,
  queryActive,
  onClear,
  datasetId,
  showDateRange = true,
}: EventFiltersBarProps) {
  const active =
    queryActive ||
    !!value.eventType ||
    !!value.category ||
    !!value.status ||
    value.isVerified != null ||
    !!value.dateFrom ||
    !!value.dateTo;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={value.eventType ?? ALL}
        onValueChange={(v) =>
          onChange({ ...value, eventType: v === ALL ? undefined : (v as EventFilters["eventType"]) })
        }
      >
        <SelectTrigger className="h-8 w-40 bg-muted/40 text-xs">
          <SelectValue placeholder="Any type" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL} className="text-xs">
            Any type
          </SelectItem>
          <SelectSeparator />
          {EVENT_TYPES.map((t) => {
            const meta = EVENT_TYPE_META[t];
            return (
              <SelectItem key={t} value={t} className="text-xs">
                <span className="flex items-center gap-2">
                  <meta.Icon size={12} className="text-muted-foreground" />
                  {meta.label}
                </span>
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>

      <Select
        value={value.status ?? ALL}
        onValueChange={(v) =>
          onChange({ ...value, status: v === ALL ? undefined : (v as EventFilters["status"]) })
        }
      >
        <SelectTrigger className="h-8 w-36 bg-muted/40 text-xs">
          <SelectValue placeholder="Any status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL} className="text-xs">
            Any status
          </SelectItem>
          <SelectSeparator />
          {EVENT_STATUSES.map((s) => (
            <SelectItem key={s} value={s} className="text-xs capitalize">
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={value.isVerified == null ? ALL : value.isVerified ? "yes" : "no"}
        onValueChange={(v) => onChange({ ...value, isVerified: v === ALL ? undefined : v === "yes" })}
      >
        <SelectTrigger className="h-8 w-36 bg-muted/40 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL} className="text-xs">
            Any review
          </SelectItem>
          <SelectItem value="yes" className="text-xs">
            Verified
          </SelectItem>
          <SelectItem value="no" className="text-xs">
            Unverified
          </SelectItem>
        </SelectContent>
      </Select>

      <SourceLabelFilter
        value={value.category}
        datasetId={datasetId}
        onChange={(category) => onChange({ ...value, category })}
      />

      {showDateRange && (
        <DateRangePicker
          value={{ from: value.dateFrom, to: value.dateTo }}
          onChange={(range) => onChange({ ...value, dateFrom: range.from, dateTo: range.to })}
        />
      )}

      {active && (
        <Button
          variant="ghost"
          size="sm"
          className="h-8 gap-1 px-2 text-xs text-muted-foreground"
          onClick={onClear}
        >
          <X size={12} />
          Clear
        </Button>
      )}
    </div>
  );
}

/**
 * Filter on a raw source label (iCalendar `CATEGORIES` — what `.ics` events
 * carry, distinct from the derived colour category). A combobox over the labels
 * that actually exist in the data, so the analyst picks rather than guesses;
 * free text still works for a value not in the list.
 */
function SourceLabelFilter({
  value,
  datasetId,
  onChange,
}: {
  value?: string;
  datasetId?: string;
  onChange: (category: string | undefined) => void;
}) {
  const [draft, setDraft] = useState(value ?? "");
  const [prev, setPrev] = useState(value);
  if (value !== prev) {
    setPrev(value);
    setDraft(value ?? "");
  }

  const { data: options = [], isFetching } = useEventCategoryOptions({
    datasetId,
    q: draft.trim() || undefined,
  });

  const commit = (v: string) => onChange(v.trim() || undefined);

  return (
    <div
      className="relative"
      title="Source label — iCalendar CATEGORIES on the event; not the colour category"
    >
      <Autocomplete className="w-48">
        <div className="flex items-center gap-1 rounded-md border border-border bg-muted/40 pl-2">
          <Tag size={12} className="shrink-0 text-muted-foreground" />
          <AutocompleteInput
            value={draft}
            onValueChange={setDraft}
            onEnter={commit}
            placeholder="Any source label"
            aria-label="Filter by source label (iCalendar CATEGORIES)"
            className="h-8 border-0 bg-transparent px-1 text-xs focus-visible:ring-0"
          />
          {value && (
            <button
              type="button"
              aria-label="Clear source label filter"
              className="pr-1.5 text-muted-foreground hover:text-foreground"
              onClick={() => {
                setDraft("");
                onChange(undefined);
              }}
            >
              <X size={12} />
            </button>
          )}
        </div>
        <AutocompleteContent
          isLoading={isFetching}
          emptyMessage={draft ? "No matching labels" : "No source labels in this data"}
        >
          {options.map((o) => (
            <AutocompleteItem key={o} value={o} selected={o === value} onSelect={() => commit(o)}>
              {o}
            </AutocompleteItem>
          ))}
        </AutocompleteContent>
      </Autocomplete>
    </div>
  );
}
