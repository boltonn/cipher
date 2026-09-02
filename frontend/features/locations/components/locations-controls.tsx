"use client";

import { Input } from "@/components/ui/input";
import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import { legendEntries, type MarkerPalette } from "@/features/locations/lib/marker-style";
import { useMapStyleStore } from "@/features/locations/style-store";
import type { LocationFeature, LocationFilters } from "@/features/locations/types";

interface LocationsControlsProps {
  filters: LocationFilters;
  onChange: (filters: LocationFilters) => void;
  features: LocationFeature[];
  palette: MarkerPalette;
  capped: boolean;
  isFetching: boolean;
}

/** ISO datetime string <-> yyyy-mm-dd for a native date input. */
const toDateInput = (iso?: string) => (iso ? iso.slice(0, 10) : "");
const fromDateInput = (v: string) => (v ? new Date(v).toISOString() : undefined);

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

  return (
    <div className="absolute left-4 top-4 z-20 w-72 rounded-xl border bg-popover/95 p-3 text-popover-foreground shadow-lg backdrop-blur">
      <div className="space-y-2.5">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Datasets</label>
          <DatasetMultiSelectCombobox
            value={filters.datasetIds}
            onChange={(datasetIds) => onChange({ ...filters, datasetIds })}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">From</label>
            <Input
              type="date"
              value={toDateInput(filters.dateFrom)}
              max={toDateInput(filters.dateTo) || undefined}
              onChange={(e) => onChange({ ...filters, dateFrom: fromDateInput(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">To</label>
            <Input
              type="date"
              value={toDateInput(filters.dateTo)}
              min={toDateInput(filters.dateFrom) || undefined}
              onChange={(e) => onChange({ ...filters, dateTo: fromDateInput(e.target.value) })}
            />
          </div>
        </div>
      </div>

      {legend.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 border-t pt-2">
          {legend.map((entry) => (
            <span key={entry.value} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="size-2 rounded-full" style={{ background: entry.color }} />
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
