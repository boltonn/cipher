import type {
  BBox,
  LocationFeatureCollection,
  LocationFilters,
} from "@/features/locations/types";
import { apiClient } from "@/lib/api-client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

const locationsBaseURL = "/locations";

export const locationsService = {
  // GET /locations -> GeoJSON FeatureCollection
  list: (filters: LocationFilters, bbox?: BBox): Promise<LocationFeatureCollection> =>
    apiClient
      .get<LocationFeatureCollection>(locationsBaseURL, {
        params: {
          bbox: bbox ? bbox.join(",") : undefined,
          datasetIds: filters.datasetIds.length ? filters.datasetIds : undefined,
          sources: filters.sources.length ? filters.sources : undefined,
          categories: filters.categories.length ? filters.categories : undefined,
          dateFrom: filters.dateFrom,
          dateTo: filters.dateTo,
          limit: 10000,
        },
      })
      .then((res) => res.data),

  // GET /locations/categories -> distinct categories, most common first
  categories: (): Promise<string[]> =>
    apiClient.get<string[]>(`${locationsBaseURL}/categories`).then((res) => res.data),
};

/** Points for the current filters + map viewport. `bbox` changes on pan/zoom. */
export function useLocations(filters: LocationFilters, bbox: BBox | undefined) {
  return useQuery({
    queryKey: ["locations", filters, bbox],
    queryFn: () => locationsService.list(filters, bbox),
    enabled: !!bbox,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

/** Distinct categories present among locations, for the category filter. */
export function useLocationCategories() {
  return useQuery({
    queryKey: ["locations", "categories"],
    queryFn: locationsService.categories,
    staleTime: 5 * 60_000,
  });
}
