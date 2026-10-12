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
import { EventLinkFilter } from "@/features/events/components/event-link-filter";
import { EVENT_TYPE_META } from "@/features/events/components/event-type-meta";
import {
  EVENT_STATUSES,
  EVENT_TYPES,
  type EventFilters,
  type EventLinkPick,
} from "@/features/events/types";
import { ActiveFilters, type ActiveFilter } from "@/components/active-filters";
import { format, parseISO } from "date-fns";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  BadgeCheck,
  CalendarRange,
  CircleDot,
  Info,
  MapPin,
  Plus,
  Search,
  Tag,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";

const ALL = "__all__";

interface EventFiltersBarProps {
  value: EventFilters;
  onChange: (next: EventFilters) => void;
  /** The committed title search, shown as a chip; removing it calls `onClearQuery`. */
  query?: string;
  onClearQuery?: () => void;
  onClear: () => void;
  datasetIds?: string[];
  /** The calendar drives its own date window via month nav, so hide the range picker there. */
  showDateRange?: boolean;
}

export function EventFiltersBar({
  value,
  onChange,
  query,
  onClearQuery,
  onClear,
  datasetIds,
  showDateRange = true,
}: EventFiltersBarProps) {
  const set = (patch: Partial<EventFilters>) =>
    onChange({ ...value, ...patch });
  const typeMeta = value.eventType ? EVENT_TYPE_META[value.eventType] : null;
  const chips: (ActiveFilter | false)[] = [
    !!query &&
      !!onClearQuery && {
        key: "query",
        label: `Title: “${query}”`,
        icon: <Search />,
        onRemove: onClearQuery,
      },
    ...(value.participants ?? []).map((p) => ({
      key: `who:${p.id ?? p.name}`,
      label: p.name,
      icon: <Users />,
      onRemove: () => set({ participants: without(value.participants, p) }),
    })),
    ...(value.places ?? []).map((p) => ({
      key: `where:${p.id ?? p.name}`,
      label: p.name,
      icon: <MapPin />,
      onRemove: () => set({ places: without(value.places, p) }),
    })),
    !!typeMeta && {
      key: "type",
      label: typeMeta.label,
      icon: <typeMeta.Icon />,
      onRemove: () => set({ eventType: undefined }),
    },
    !!value.status && {
      key: "status",
      label: capitalize(value.status),
      icon: <CircleDot />,
      onRemove: () => set({ status: undefined }),
    },
    value.isVerified != null && {
      key: "review",
      label: value.isVerified ? "Verified" : "Unverified",
      icon: <BadgeCheck />,
      onRemove: () => set({ isVerified: undefined }),
    },
    !!value.category && {
      key: "label",
      label: `Label: ${value.category}`,
      icon: <Tag />,
      onRemove: () => set({ category: undefined }),
    },
    showDateRange &&
      !!(value.dateFrom || value.dateTo) && {
        key: "date",
        label: dateLabel(value.dateFrom, value.dateTo),
        icon: <CalendarRange />,
        onRemove: () => set({ dateFrom: undefined, dateTo: undefined }),
      },
  ];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={value.eventType ?? ALL}
          onValueChange={(v) =>
            onChange({
              ...value,
              eventType:
                v === ALL ? undefined : (v as EventFilters["eventType"]),
            })
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

        <EventLinkFilter
          kind="participant"
          value={value.participants}
          datasetIds={datasetIds}
          onChange={(participants) => onChange({ ...value, participants })}
        />

        <EventLinkFilter
          kind="place"
          value={value.places}
          datasetIds={datasetIds}
          onChange={(places) => onChange({ ...value, places })}
        />

        <Select
          value={value.status ?? ALL}
          onValueChange={(v) =>
            onChange({
              ...value,
              status: v === ALL ? undefined : (v as EventFilters["status"]),
            })
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
          value={
            value.isVerified == null ? ALL : value.isVerified ? "yes" : "no"
          }
          onValueChange={(v) =>
            onChange({
              ...value,
              isVerified: v === ALL ? undefined : v === "yes",
            })
          }
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
          datasetIds={datasetIds}
          onChange={(category) => onChange({ ...value, category })}
        />

        {showDateRange && (
          <DateRangePicker
            value={{ from: value.dateFrom, to: value.dateTo }}
            onChange={(range) =>
              onChange({ ...value, dateFrom: range.from, dateTo: range.to })
            }
          />
        )}
      </div>
      <ActiveFilters
        filters={chips.filter((c) => c !== false)}
        onClearAll={onClear}
      />
    </div>
  );
}

const without = (picks: EventLinkPick[] = [], pick: EventLinkPick) => {
  const next = picks.filter((p) => (p.id ?? p.name) !== (pick.id ?? pick.name));
  return next.length ? next : undefined;
};

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function dateLabel(from?: string, to?: string) {
  const day = (iso: string) => format(parseISO(iso), "d MMM yyyy");
  if (from && to) return `${day(from)} – ${day(to)}`;
  return from ? `From ${day(from)}` : `Until ${day(to as string)}`;
}

const SOURCE_LABEL_HELP =
  "Labels the calendar app itself put on the event (iCalendar CATEGORIES) — free-form and inconsistent across sources. Filter by Type first; use this only to chase a specific label from the data.";

/**
 * Filter on a raw source label (iCalendar `CATEGORIES`), distinct from our
 * event types. Collapsed behind a quiet toggle (absent when the data has no labels) so
 * analysts reach for Type first; stays open while a label is applied. Typeahead over labels that exist in the
 * data; free text still works for a value not in the list.
 */
function SourceLabelFilter({
  value,
  datasetIds,
  onChange,
}: {
  value?: string;
  datasetIds?: string[];
  onChange: (category: string | undefined) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [prev, setPrev] = useState(value);
  if (value !== prev) {
    setPrev(value);
    setDraft(value ?? "");
    if (!value) setIsExpanded(false);
  }

  const isOpen = isExpanded || !!value;
  const { data: options = [], isFetching } = useEventCategoryOptions({
    datasetIds,
    q: draft.trim() || undefined,
  });

  const commit = (v: string) => onChange(v.trim() || undefined);
  const clear = () => {
    setDraft("");
    setIsExpanded(false);
    onChange(undefined);
  };

  if (!isOpen) {
    if (!options.length) return null;
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5 px-2 text-xs text-muted-foreground"
            onClick={() => setIsExpanded(true)}
          >
            <Plus size={12} />
            Source label
          </Button>
        </TooltipTrigger>
        <TooltipContent className="max-w-64">
          {SOURCE_LABEL_HELP}
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Autocomplete className="w-56">
      <AutocompleteInput
        autoFocus={!value}
        value={draft}
        onValueChange={setDraft}
        onEnter={commit}
        onBlur={() => {
          if (draft.trim() !== (value ?? "")) commit(draft);
          else if (!value) setIsExpanded(false);
        }}
        placeholder="Source label…"
        aria-label="Filter by source label (iCalendar CATEGORIES)"
        className="h-8 gap-1.5 rounded-lg border-input bg-muted/40 px-2 py-0 text-xs focus-within:ring-0 focus-within:border-ring"
        startAddon={
          <Tooltip>
            <TooltipTrigger asChild>
              <Info
                size={12}
                className="shrink-0 text-muted-foreground"
                aria-label="About source labels"
              />
            </TooltipTrigger>
            <TooltipContent className="max-w-64">
              {SOURCE_LABEL_HELP}
            </TooltipContent>
          </Tooltip>
        }
        endAddon={
          <button
            type="button"
            aria-label="Remove source label filter"
            className="shrink-0 text-muted-foreground hover:text-foreground"
            onClick={clear}
          >
            <X size={12} />
          </button>
        }
      />
      <AutocompleteContent
        isLoading={isFetching}
        emptyMessage={
          draft
            ? "No matching labels — Enter to filter anyway"
            : "No source labels in this data"
        }
      >
        {options.map((o) => (
          <AutocompleteItem
            key={o}
            value={o}
            selected={o === value}
            onSelect={() => commit(o)}
          >
            {o}
          </AutocompleteItem>
        ))}
      </AutocompleteContent>
    </Autocomplete>
  );
}
