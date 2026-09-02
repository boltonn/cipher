"use client";

import { useLocations } from "@/features/locations/api";
import {
  LocationDetailPanel,
  type SelectedLocation,
} from "@/features/locations/components/location-detail-panel";
import { LocationsControls } from "@/features/locations/components/locations-controls";
import { LocationsMap } from "@/features/locations/components/locations-map";
import { useMarkerPalette } from "@/features/locations/lib/use-marker-palette";
import { EMPTY_LOCATION_FILTERS, type BBox, type LocationFilters } from "@/features/locations/types";
import { useState } from "react";

/** Server also caps at this; past it the map asks the user to zoom in or filter. */
const RESULT_CAP = 10000;

export default function LocationsPage() {
  const [filters, setFilters] = useState<LocationFilters>(EMPTY_LOCATION_FILTERS);
  const [bbox, setBbox] = useState<BBox>();
  const [selected, setSelected] = useState<SelectedLocation | null>(null);
  const palette = useMarkerPalette();

  const { data, isFetching } = useLocations(filters, bbox);
  const features = data?.features ?? [];

  return (
    <div className="relative h-full w-full">
      <LocationsMap
        features={features}
        palette={palette}
        onBoundsChange={setBbox}
        onSelect={setSelected}
      />
      <LocationsControls
        filters={filters}
        onChange={setFilters}
        features={features}
        palette={palette}
        capped={features.length >= RESULT_CAP}
        isFetching={isFetching}
      />
      <LocationDetailPanel feature={selected} palette={palette} onClose={() => setSelected(null)} />
    </div>
  );
}
