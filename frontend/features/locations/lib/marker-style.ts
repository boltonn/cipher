import { colorFor } from "@/features/locations/lib/category-icons";
import type { LocationFeature } from "@/features/locations/types";

/** Which feature property drives the marker colour. */
export type ColorField = "source" | "category";

export const COLOR_FIELDS: { id: ColorField; label: string }[] = [
  { id: "source", label: "Source" },
  { id: "category", label: "Category" },
];

const FALLBACK_RGB = "#6366f1";

/**
 * Normalise a CSS var name or any CSS colour string to an `rgb()/rgba()` value.
 *
 * We paint one pixel and read it back rather than trusting `ctx.fillStyle`,
 * which some browsers normalise to `lab()` / `oklch()` -- syntaxes maplibre's
 * style parser rejects ("color expected, \"lab(...)\" found").
 */
export function resolveCssColor(token: string): string {
  if (typeof document === "undefined") return FALLBACK_RGB;
  let raw = token;
  if (raw.startsWith("--")) {
    raw = getComputedStyle(document.documentElement).getPropertyValue(raw).trim();
  }
  if (!raw) return FALLBACK_RGB;
  try {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (ctx) {
      ctx.fillStyle = "#010203"; // sentinel: unchanged if the browser can't parse `raw`
      ctx.fillStyle = raw;
      if (ctx.fillStyle === "#010203") return FALLBACK_RGB;
      ctx.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
      return a === 255 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
    }
  } catch {
    /* fall through */
  }
  return FALLBACK_RGB;
}

export interface MarkerPalette {
  fallback: string;
  cluster: string;
  clusterText: string;
  pointStroke: string;
}

/** Resolve the theme-tracking colours once (call again on a theme change). */
export function buildMarkerPalette(): MarkerPalette {
  return {
    fallback: resolveCssColor("--muted-foreground"),
    cluster: resolveCssColor("--primary"),
    clusterText: resolveCssColor("--foreground"),
    pointStroke: resolveCssColor("--background"),
  };
}

/**
 * Fixed display colour for a feature's `source` / `category` value. Delegates to
 * `category-icons` so markers, legend, and detail header always agree.
 */
export function colorForValue(
  _palette: MarkerPalette,
  field: ColorField,
  value: string | null | undefined,
): string {
  return colorFor(field, value);
}

/** Feature with a `markerColor` property so the circle layer can `["get", "markerColor"]`. */
export function withMarkerColor(
  feature: LocationFeature,
  field: ColorField,
  palette: MarkerPalette,
): LocationFeature {
  const raw = field === "source" ? feature.properties.source : feature.properties.category;
  return {
    ...feature,
    properties: { ...feature.properties, markerColor: colorForValue(palette, field, raw) },
  } as LocationFeature;
}

/** Distinct (value, colour) pairs present in the current result set, for a legend. */
export function legendEntries(
  features: LocationFeature[],
  field: ColorField,
  palette: MarkerPalette,
): { value: string; color: string }[] {
  const seen = new Map<string, string>();
  for (const f of features) {
    const raw = field === "source" ? f.properties.source : f.properties.category;
    const value = raw || "unknown";
    if (!seen.has(value)) seen.set(value, colorForValue(palette, field, raw));
  }
  return [...seen.entries()].map(([value, color]) => ({ value, color }));
}
