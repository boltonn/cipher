"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import { Button } from "@/components/ui/button";
import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import { MarkerIcon } from "@/features/locations/lib/category-icons";
import { legendEntries, type MarkerPalette } from "@/features/locations/lib/marker-style";
import { useMapStyleStore } from "@/features/locations/style-store";
import type { LocationFeature, LocationFilters } from "@/features/locations/types";
import { SlidersHorizontal, X } from "lucide-react";
import { useState } from "react";

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

  const activeFilters =
    (filters.datasetIds?.length ?? 0) + (filters.dateFrom ? 1 : 0) + (filters.dateTo ? 1 : 0);

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
          <span className="rounded-full bg-primary/15 px-1.5 text-[10px] font-bold text-primary">
            {activeFilters}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="absolute left-4 top-4 z-20 w-72 rounded-xl border bg-popover/95 p-3 text-popover-foreground shadow-lg backdrop-blur">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Filters
        </span>
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
          />
        </div>
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
              {entry.value.replace(/_/g, " ")}
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
