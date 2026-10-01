"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import { Button } from "@/components/ui/button";
import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import { useLocationCategories } from "@/features/locations/api";
import { colorFor, labelFor, MarkerIcon } from "@/features/locations/lib/category-icons";
import {
  legendEntries,
  type ColorField,
  type MarkerPalette,
} from "@/features/locations/lib/marker-style";
import { useMapStyleStore } from "@/features/locations/style-store";
import {
  EMPTY_LOCATION_FILTERS,
  LOCATION_SOURCES,
  type LocationFeature,
  type LocationFilters,
} from "@/features/locations/types";
import { cn } from "@/lib/utils";
import { SlidersHorizontal, X } from "lucide-react";
import { useState } from "react";

/** Toggle chips for one multi-value filter (`sources` / `categories`). */
function ValueChips<T extends string>({
  field,
  options,
  value,
  onChange,
}: {
  field: ColorField;
  options: T[];
  value: T[];
  onChange: (value: T[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const active = value.includes(option);
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            onClick={() =>
              onChange(active ? value.filter((v) => v !== option) : [...value, option])
            }
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs transition-colors",
              active
                ? "border-primary/40 bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <MarkerIcon
              field={field}
              value={option}
              className="size-3 shrink-0"
              style={{ color: colorFor(field, option) }}
            />
            {labelFor(field, option)}
          </button>
        );
      })}
    </div>
  );
}

interface LocationsControlsProps {
  filters: LocationFilters;
  onChange: (filters: LocationFilters) => void;
  features: LocationFeature[];
  palette: MarkerPalette;
  capped: boolean;
  isFetching: boolean;
}

export function LocationsControls({
  filters,
  onChange,
  features,
  palette,
  capped,
  isFetching,
}: LocationsControlsProps) {
  const colorField = useMapStyleStore((s) => s.colorField);
  const legend = legendEntries(features, colorField, palette);
  const count = features.length;
  const [open, setOpen] = useState(true);

  const { data: categories = [] } = useLocationCategories();

  const activeFilters =
    filters.datasetIds.length +
    filters.sources.length +
    filters.categories.length +
    (filters.dateFrom ? 1 : 0) +
    (filters.dateTo ? 1 : 0);

  // Collapsed: a single chip that stays out of the map's way but keeps the
  // point count and a way back to the filters visible.
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-lg border bg-popover/95 px-3 py-2 text-xs text-popover-foreground shadow-lg backdrop-blur hover:bg-popover"
      >
        <SlidersHorizontal size={13} className="text-primary" />
        <span>{isFetching ? "Loading…" : `${count.toLocaleString()} points`}</span>
        {activeFilters > 0 && (
          <span className="rounded-full bg-primary/15 px-1.5 text-[11px] font-bold text-primary">
            {activeFilters}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="absolute left-4 top-4 z-20 w-72 rounded-xl border bg-popover/95 p-3 text-popover-foreground shadow-lg backdrop-blur">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
          Filters
        </span>
        <div className="flex items-center gap-1">
          {activeFilters > 0 && (
            <button
              type="button"
              onClick={() => onChange(EMPTY_LOCATION_FILTERS)}
              className="px-1 text-xs text-muted-foreground hover:text-foreground"
            >
              Reset
            </button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Collapse filters"
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            onClick={() => setOpen(false)}
          >
            <X size={13} />
          </Button>
        </div>
      </div>

      <div className="space-y-2.5">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Datasets</label>
          <DatasetMultiSelectCombobox
            value={filters.datasetIds}
            onChange={(datasetIds) => onChange({ ...filters, datasetIds })}
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Date range</label>
          <DateRangePicker
            value={{ from: filters.dateFrom, to: filters.dateTo }}
            onChange={(range) =>
              onChange({ ...filters, dateFrom: range.from, dateTo: range.to })
            }
            placeholder="Any date"
            className="h-9"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Source</label>
          <ValueChips
            field="source"
            options={LOCATION_SOURCES}
            value={filters.sources}
            onChange={(sources) => onChange({ ...filters, sources })}
          />
        </div>
        {categories.length > 0 && (
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Category</label>
            <ValueChips
              field="category"
              options={categories}
              value={filters.categories}
              onChange={(categories) => onChange({ ...filters, categories })}
            />
          </div>
        )}
      </div>

      {legend.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 border-t pt-2">
          {legend.map((entry) => (
            <span
              key={entry.value}
              className="flex items-center gap-1.5 text-xs text-muted-foreground"
            >
              <MarkerIcon
                field={colorField}
                value={entry.value === "unknown" ? null : entry.value}
                className="size-3 shrink-0"
                style={{ color: entry.color }}
              />
              {labelFor(colorField, entry.value)}
            </span>
          ))}
        </div>
      )}

      <p className="mt-2 border-t pt-2 text-xs text-muted-foreground">
        {isFetching
          ? "Loading…"
          : capped
            ? `Showing first ${count.toLocaleString()} — zoom in or filter for more`
            : `${count.toLocaleString()} point${count === 1 ? "" : "s"}`}
      </p>
    </div>
  );
}
