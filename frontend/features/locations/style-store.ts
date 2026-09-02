import type { ColorField } from "@/features/locations/lib/marker-style";
import type { StyleSpecification } from "maplibre-gl";
import { create } from "zustand";
import { persist } from "zustand/middleware";

/** Glyphs for the raster styles' cluster-count labels (bare raster styles ship none). */
const GLYPHS = "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf";

function raster(tiles: string[], attribution = ""): StyleSpecification {
  return {
    version: 8,
    glyphs: GLYPHS,
    sources: { base: { type: "raster", tiles, tileSize: 256, attribution } },
    layers: [{ id: "base", type: "raster", source: "base" }],
  };
}

export interface MapStyleOption {
  id: string;
  label: string;
  /** A MapLibre style: a hosted style-JSON URL, or an inline spec (raster). */
  style: string | StyleSpecification;
}

export const MAP_STYLES: MapStyleOption[] = [
  { id: "map", label: "Map", style: raster(["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]) },
  {
    id: "light",
    label: "Light",
    style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  },
  {
    id: "dark",
    label: "Dark",
    style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  },
  {
    id: "satellite",
    label: "Satellite",
    style: raster([
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    ]),
  },
];

export function mapStyle(id: string): string | StyleSpecification {
  return (MAP_STYLES.find((s) => s.id === id) ?? MAP_STYLES[0]).style;
}

interface MapStyleState {
  styleId: string;
  setStyleId: (styleId: string) => void;
  colorField: ColorField;
  setColorField: (colorField: ColorField) => void;
}

export const useMapStyleStore = create<MapStyleState>()(
  persist(
    (set) => ({
      styleId: MAP_STYLES[0].id,
      setStyleId: (styleId) => set({ styleId }),
      colorField: "source",
      setColorField: (colorField) => set({ colorField }),
    }),
    { name: "locations-map-v3" },
  ),
);
