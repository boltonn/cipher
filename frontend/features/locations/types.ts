/** Mirrors `cipher.schemas.graph.ontology.LocationSource`. */
export type LocationSource =
  | "name_mention"
  | "coordinate_mention"
  | "exif"
  | "geocoded"
  | "device_gps";

export interface LocationProperties {
  id: string;
  name: string | null;
  category: string | null;
  source: LocationSource;
  dateRecorded: string | null;
  bearing: number | null;
  velocity: number | null;
  altitude: number | null;
  fileId: string | null;
  /** sha256 of the source image, resolved from `fileId` server-side; null if the file isn't an image. */
  imageId: string | null;
  datasetId: string | null;
  /** Added client-side from the "colour points by" setting; not sent by the API. */
  markerColor?: string;
}

export interface LocationFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] } | null;
  properties: LocationProperties;
}

export interface LocationFeatureCollection {
  type: "FeatureCollection";
  features: LocationFeature[];
}

export const LOCATION_SOURCES: LocationSource[] = [
  "name_mention",
  "coordinate_mention",
  "exif",
  "geocoded",
  "device_gps",
];

/** One object for the whole filter surface, per the app's schema-object convention. */
export interface LocationFilters {
  datasetIds: string[];
  sources: LocationSource[];
  categories: string[];
  dateFrom?: string;
  dateTo?: string;
}

export const EMPTY_LOCATION_FILTERS: LocationFilters = {
  datasetIds: [],
  sources: [],
  categories: [],
};

/** [west, south, east, north] */
export type BBox = [number, number, number, number];
