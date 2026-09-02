import type { LocationFeature } from "@/features/locations/types";

/** Which feature property drives the marker colour. */
export type ColorField = "source" | "category";

export const COLOR_FIELDS: { id: ColorField; label: string }[] = [
  { id: "source", label: "Source" },
  { id: "category", label: "Category" },
];

/**
 * Colours are design-token names (or literal hex where the app has no matching
 * token) resolved to concrete rgb at runtime -- maplibre paint can't read CSS
 * variables, and we want the map to track the app's theme. `exif` is the app's
 * primary; the rest are muted, harmonious hues (no amber/yellow).
 */
const SOURCE_TOKENS: Record<string, string> = {
  exif: "--primary",
  geocoded: "--highlight",
  named_mention: "#7a74d6",
  device_gps: "#3f9d6d",
};
const FALLBACK_TOKEN = "--muted-foreground";

// Categorical hues -- app tokens first, then a curated, yellow-free set that
// harmonises with them (all mid saturation / mid lightness).
const CATEGORY_TOKENS = [
  "--primary",
  "--highlight",
  "#3f9d6d",
  "#c65f88",
  "#7a74d6",
  "#4a90b8",
  "#b5744a",
  "#7d7f8c",
];

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

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
  source: Record<string, string>;
  category: string[];
  fallback: string;
  cluster: string;
  clusterText: string;
  pointStroke: string;
}

/** Resolve every token once (call again on a theme change). */
export function buildMarkerPalette(): MarkerPalette {
  return {
    source: Object.fromEntries(
      Object.entries(SOURCE_TOKENS).map(([k, v]) => [k, resolveCssColor(v)]),
    ),
    category: CATEGORY_TOKENS.map(resolveCssColor),
    fallback: resolveCssColor(FALLBACK_TOKEN),
    cluster: resolveCssColor("--primary"),
    clusterText: resolveCssColor("--foreground"),
    pointStroke: resolveCssColor("--background"),
  };
}

export function colorForValue(
  palette: MarkerPalette,
  field: ColorField,
  value: string | null | undefined,
): string {
  if (!value) return palette.fallback;
  if (field === "source") return palette.source[value] ?? palette.fallback;
  return palette.category[hash(value) % palette.category.length];
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
