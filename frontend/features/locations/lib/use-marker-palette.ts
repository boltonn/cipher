"use client";

import { buildMarkerPalette, type MarkerPalette } from "@/features/locations/lib/marker-style";
import { useEffect, useState } from "react";

/** Marker colours resolved from the app's CSS tokens, rebuilt when the theme changes. */
export function useMarkerPalette(): MarkerPalette {
  const [palette, setPalette] = useState<MarkerPalette>(() => buildMarkerPalette());

  useEffect(() => {
    const rebuild = () => setPalette(buildMarkerPalette());
    const observer = new MutationObserver(rebuild);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "style"],
    });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", rebuild);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", rebuild);
    };
  }, []);

  return palette;
}
