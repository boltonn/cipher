"use client";

import { LocationHoverCard, type HoverTarget } from "@/features/locations/components/location-hover-card";
import type { SelectedLocation } from "@/features/locations/components/location-detail-panel";
import { MapControls } from "@/features/locations/components/map-controls";
import { LocationPin } from "@/features/locations/lib/category-icons";
import { withMarkerColor, type MarkerPalette } from "@/features/locations/lib/marker-style";
import { mapStyle, useMapStyleStore } from "@/features/locations/style-store";
import type { BBox, LocationFeature, LocationProperties } from "@/features/locations/types";
import { Button } from "@/components/ui/button";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapPinOff, RotateCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

/** Above this many on-screen unclustered points, drop the HTML icon pins and
 *  fall back to the plain circle layer (which stays fast at any count). */
const PIN_CAP = 300;

function boundsToBBox(map: maplibregl.Map): BBox {
  const b = map.getBounds();
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
}

interface LocationsMapProps {
  features: LocationFeature[];
  palette: MarkerPalette;
  onBoundsChange: (bbox: BBox) => void;
  onSelect: (feature: SelectedLocation) => void;
}

export function LocationsMap({ features, palette, onBoundsChange, onSelect }: LocationsMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const featuresRef = useRef(features);
  const didFitRef = useRef(false);
  // Cluster-count labels are HTML markers, not a symbol layer -- symbol layers
  // need a glyph atlas (a network fetch); HTML uses the browser's own fonts and
  // works with nothing but the tile server. One marker per live cluster id.
  const clusterMarkersRef = useRef<Map<number, maplibregl.Marker>>(new Map());
  const syncClustersRef = useRef<() => void>(() => {});
  // One icon-pin HTML marker per on-screen unclustered point (shadowbot-style:
  // a solid disc reads on any basemap where a translucent circle vanishes).
  const pointMarkersRef = useRef<
    Map<string, { marker: maplibregl.Marker; root: Root; value?: string | null }>
  >(new Map());
  const syncPointsRef = useRef<() => void>(() => {});
  // True while the icon pins are up: the `unclustered-point` circle layer is
  // then painted transparent and its hover/click handlers stand down.
  const pinsActiveRef = useRef(false);
  const [hover, setHover] = useState<HoverTarget | null>(null);
  // The basemap tiles come from an external style server. When that can't be
  // reached the map is just a black rectangle with no explanation -- track it
  // so we can say what happened instead.
  const [basemapFailed, setBasemapFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const styleId = useMapStyleStore((s) => s.styleId);
  const colorField = useMapStyleStore((s) => s.colorField);

  const colorFieldRef = useRef(colorField);
  const paletteRef = useRef(palette);
  const onBoundsChangeRef = useRef(onBoundsChange);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    colorFieldRef.current = colorField;
    paletteRef.current = palette;
    onBoundsChangeRef.current = onBoundsChange;
    onSelectRef.current = onSelect;
  });

  const buildData = (): GeoJSON.FeatureCollection => ({
    type: "FeatureCollection",
    features: featuresRef.current
      .filter((f) => f.geometry)
      .map((f) => withMarkerColor(f, colorFieldRef.current, paletteRef.current)) as GeoJSON.Feature[],
  });

  // --- one-time map setup ---
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const clusterMarkers = clusterMarkersRef.current;
    const pointMarkers = pointMarkersRef.current;

    const map = new maplibregl.Map({
      container,
      style: mapStyle(useMapStyleStore.getState().styleId),
      center: [0, 20],
      zoom: 1.6,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    setBasemapFailed(false);
    // If the style hasn't come up in a reasonable window, treat the basemap as
    // unreachable rather than leaving a silent black canvas.
    const basemapTimer = setTimeout(() => {
      if (!map.isStyleLoaded()) setBasemapFailed(true);
    }, 8000);
    map.on("load", () => {
      clearTimeout(basemapTimer);
      setBasemapFailed(false);
    });
    map.on("error", () => {
      // A transient tile 404 shouldn't blank the whole map -- only treat it as
      // a failure if the base style itself never came up.
      if (!map.isStyleLoaded()) setBasemapFailed(true);
    });

    // The container's final size can land a couple of frames after mount inside
    // the app's flex shell -- keep the map matched to its box.
    let lastW = 0;
    let lastH = 0;
    const resizeObserver = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (Math.abs(width - lastW) < 1 && Math.abs(height - lastH) < 1) return;
      lastW = width;
      lastH = height;
      map.resize();
      onBoundsChangeRef.current(boundsToBBox(map));
    });
    resizeObserver.observe(container);

    const addLocationLayers = () => {
      if (map.getSource("locations")) return;
      const p = paletteRef.current;
      map.addSource("locations", {
        type: "geojson",
        data: buildData(),
        cluster: true,
        clusterRadius: 50,
        clusterMaxZoom: 14,
      });
      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "locations",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": p.cluster,
          "circle-opacity": 0.9,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": 0.9,
          "circle-radius": ["step", ["get", "point_count"], 16, 25, 22, 100, 30],
        },
      });
      map.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: "locations",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": ["coalesce", ["get", "markerColor"], paletteRef.current.fallback],
          "circle-radius": 7,
          "circle-opacity": 0.95,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": 1,
        },
      });
      pinsActiveRef.current = false; // circles were just painted opaque
    };

    // Fade the `unclustered-point` circles to transparent while icon pins are up
    // (and back when they're not). Only touches paint on an actual flip.
    const setCirclesFaded = (faded: boolean) => {
      if (pinsActiveRef.current === faded) return;
      pinsActiveRef.current = faded;
      map.setPaintProperty("unclustered-point", "circle-opacity", faded ? 0 : 0.95);
      map.setPaintProperty("unclustered-point", "circle-stroke-opacity", faded ? 0 : 1);
    };

    const zoomToCluster = (clusterId: number, center: [number, number]) => {
      const source = map.getSource("locations") as maplibregl.GeoJSONSource;
      source.getClusterExpansionZoom(clusterId).then((zoom) => {
        map.easeTo({ center, zoom });
      });
    };

    // Keep one HTML marker per rendered cluster, showing its count. Called
    // whenever the cluster set can change (pan, zoom, new data).
    const syncClusterMarkers = () => {
      if (!map.getLayer("clusters")) return;
      const rendered = map.queryRenderedFeatures({ layers: ["clusters"] });
      const live = new Set<number>();

      for (const feat of rendered) {
        const id = feat.properties?.cluster_id as number | undefined;
        if (id == null) continue;
        live.add(id);
        const center = (feat.geometry as GeoJSON.Point).coordinates as [number, number];
        const label = String(
          feat.properties?.point_count_abbreviated ?? feat.properties?.point_count ?? "",
        );

        let marker = clusterMarkersRef.current.get(id);
        if (!marker) {
          const el = document.createElement("button");
          el.type = "button";
          el.className = "maplibre-cluster-count";
          // Neutralise the <button> UA chrome WITHOUT `all:unset` -- that also
          // wipes the `position:absolute` the `.maplibregl-marker` class relies
          // on, which left every count label stacked at the container origin
          // instead of on its cluster. White text + dark halo stays legible on
          // a light, dark, or satellite basemap alike.
          el.style.cssText =
            "position:absolute;top:0;left:0;appearance:none;-webkit-appearance:none;" +
            "border:0;background:transparent;margin:0;cursor:pointer;" +
            "font:700 11px/1 var(--font-sans,system-ui),sans-serif;letter-spacing:.02em;" +
            "display:flex;align-items:center;justify-content:center;" +
            "min-width:20px;height:20px;padding:0 4px;color:#fff;" +
            "text-shadow:0 0 3px rgba(0,0,0,.9),0 1px 2px rgba(0,0,0,.65);";
          marker = new maplibregl.Marker({ element: el })
            .setLngLat(center)
            .addTo(map);
          clusterMarkersRef.current.set(id, marker);
        }
        const el = marker.getElement();
        if (el.textContent !== label) el.textContent = label;
        el.onclick = () => zoomToCluster(id, center);
        marker.setLngLat(center);
      }

      for (const [id, marker] of clusterMarkersRef.current) {
        if (!live.has(id)) {
          marker.remove();
          clusterMarkersRef.current.delete(id);
        }
      }
    };
    syncClustersRef.current = syncClusterMarkers;

    const removePin = (entry: { marker: maplibregl.Marker; root: Root }) => {
      entry.marker.remove();
      // Defer: unmounting a root synchronously from inside React's commit throws.
      queueMicrotask(() => entry.root.unmount());
    };

    // One icon pin per on-screen unclustered point. While the pins are up the
    // `unclustered-point` circle layer is painted transparent, so hover and
    // click are wired straight onto the pin elements.
    const syncPointMarkers = () => {
      if (!map.getLayer("unclustered-point")) return;
      const rendered = map.queryRenderedFeatures({ layers: ["unclustered-point"] });
      const field = colorFieldRef.current;

      // `queryRenderedFeatures` still returns features from an opacity-0 layer
      // (it wouldn't from a `visibility:none` one), so fade the circles rather
      // than hiding the layer -- that keeps this query working next tick.
      if (rendered.length > PIN_CAP) {
        for (const entry of pointMarkersRef.current.values()) removePin(entry);
        pointMarkersRef.current.clear();
        setCirclesFaded(false);
        return;
      }
      setCirclesFaded(true);

      const live = new Set<string>();
      for (const feat of rendered) {
        const props = feat.properties as unknown as LocationProperties;
        const id = props.id;
        if (!id) continue;
        live.add(id);
        const center = (feat.geometry as GeoJSON.Point).coordinates as [number, number];
        const value = (field === "source" ? props.source : props.category) ?? null;
        const renderKey = `${field}:${value ?? ""}`;

        let entry = pointMarkersRef.current.get(id);
        if (!entry) {
          const el = document.createElement("div");
          el.style.cssText = "line-height:0;cursor:pointer;";
          const root = createRoot(el);
          const marker = new maplibregl.Marker({ element: el }).setLngLat(center).addTo(map);
          entry = { marker, root };
          pointMarkersRef.current.set(id, entry);
        }
        entry.marker.setLngLat(center);
        if (entry.value !== renderKey) {
          entry.root.render(<LocationPin field={field} value={value} />);
          entry.value = renderKey;
        }
        const el = entry.marker.getElement();
        el.onmouseenter = () => {
          const pt = map.project(center);
          setHover({ props: props as unknown as HoverTarget["props"], x: pt.x, y: pt.y });
        };
        el.onmouseleave = () => setHover(null);
        el.onclick = () => {
          const [lng, lat] = center;
          onSelectRef.current({ ...(props as unknown as SelectedLocation), lng, lat });
        };
      }

      for (const [id, entry] of pointMarkersRef.current) {
        if (!live.has(id)) {
          removePin(entry);
          pointMarkersRef.current.delete(id);
        }
      }
    };
    syncPointsRef.current = syncPointMarkers;

    const emitBounds = () => onBoundsChangeRef.current(boundsToBBox(map));

    // Bounds -> parent drives the data fetch. Don't gate it on `load` (a slow
    // vector style can delay or swallow that); fire on move and whenever the
    // style becomes ready.
    map.on("moveend", () => {
      emitBounds();
      syncClusterMarkers();
      syncPointMarkers();
    });
    map.on("load", () => {
      addLocationLayers();
      emitBounds();
    });
    map.on("styledata", () => {
      if (!map.isStyleLoaded()) return;
      if (!map.getSource("locations")) addLocationLayers();
      emitBounds();
    });
    map.on("sourcedata", (e) => {
      if (e.sourceId === "locations" && e.isSourceLoaded) {
        syncClusterMarkers();
        syncPointMarkers();
      }
    });
    // `sourcedata` / `moveend` can fire before the cluster circles are actually
    // painted, so `queryRenderedFeatures` finds nothing and no count markers get
    // made. `idle` fires once the map has finished rendering -- the reliable
    // point to (re)build the HTML markers. It's also the backstop for adding the
    // layers if `load` never fired (offline tiles, backgrounded tab).
    map.on("idle", () => {
      if (!map.getSource("locations")) {
        if (map.isStyleLoaded()) addLocationLayers();
        return;
      }
      if (!map.isSourceLoaded("locations")) return;
      syncClusterMarkers();
      syncPointMarkers();
    });
    // If the style is ready before any handler is wired, add layers now.
    if (map.isStyleLoaded() && !map.getSource("locations")) addLocationLayers();

    map.on("click", "clusters", (e) => {
      const feat = map.queryRenderedFeatures(e.point, { layers: ["clusters"] })[0];
      zoomToCluster(
        feat.properties?.cluster_id as number,
        (feat.geometry as GeoJSON.Point).coordinates as [number, number],
      );
    });
    // These fire only in the >PIN_CAP fallback (no pins); with pins up, the pin
    // elements own hover/click.
    map.on("mousemove", "unclustered-point", (e) => {
      if (pinsActiveRef.current) return;
      map.getCanvas().style.cursor = "pointer";
      const feat = e.features?.[0];
      if (!feat) return;
      setHover({ props: feat.properties as unknown as HoverTarget["props"], x: e.point.x, y: e.point.y });
    });
    map.on("mouseleave", "unclustered-point", () => {
      if (pinsActiveRef.current) return;
      map.getCanvas().style.cursor = "";
      setHover(null);
    });
    map.on("click", "unclustered-point", (e) => {
      if (pinsActiveRef.current) return;
      const feat = e.features?.[0];
      if (!feat) return;
      const [lng, lat] = (feat.geometry as GeoJSON.Point).coordinates as [number, number];
      onSelectRef.current({ ...(feat.properties as unknown as SelectedLocation), lng, lat });
    });

    return () => {
      clearTimeout(basemapTimer);
      resizeObserver.disconnect();
      clusterMarkers.forEach((m) => m.remove());
      clusterMarkers.clear();
      pointMarkers.forEach(removePin);
      pointMarkers.clear();
      map.remove();
      mapRef.current = null;
    };
  }, [reloadKey]);

  // --- basemap style switch. Track the last id we actually applied: the map
  // constructor already used the current one, and a bare "skip first run" guard
  // still re-fires under StrictMode's double-invoke, calling setStyle mid-load
  // ("Unable to perform style diff... Rebuilding from scratch") which wipes the
  // freshly added layers. ---
  const appliedStyleRef = useRef<string | null>(null);
  useEffect(() => {
    if (appliedStyleRef.current === null) {
      appliedStyleRef.current = styleId; // constructor already set this one
      return;
    }
    if (appliedStyleRef.current === styleId) return;
    appliedStyleRef.current = styleId;
    mapRef.current?.setStyle(mapStyle(styleId));
  }, [styleId]);

  // --- data / colour-field / theme updates ---
  useEffect(() => {
    featuresRef.current = features;
    const map = mapRef.current;
    if (!map) return;

    const source = map.getSource("locations") as maplibregl.GeoJSONSource | undefined;
    source?.setData(buildData());

    if (map.getLayer("clusters")) {
      map.setPaintProperty("clusters", "circle-color", palette.cluster);
    }
    // Refresh the HTML cluster-count + icon-pin markers for the new data / field.
    syncClustersRef.current();
    syncPointsRef.current();

    if (!didFitRef.current && features.length > 0) {
      const coords = features
        .map((f) => f.geometry?.coordinates)
        .filter(Boolean) as [number, number][];
      if (coords.length) {
        const bounds = coords.reduce(
          (acc, c) => acc.extend(c),
          new maplibregl.LngLatBounds(coords[0], coords[0]),
        );
        map.fitBounds(bounds, { padding: 64, maxZoom: 14, duration: 0 });
        didFitRef.current = true;
      }
    }
  }, [features, colorField, palette]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      {basemapFailed && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-background/80 px-6 text-center backdrop-blur-sm">
          <MapPinOff className="size-6 text-muted-foreground/60" />
          <p className="text-sm font-medium text-foreground">Couldn’t load the map</p>
          <p className="max-w-xs text-xs text-muted-foreground">
            The basemap tiles didn’t load. Your points are still here — retry once
            you have a connection.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-1 h-8 gap-1.5 text-xs"
            onClick={() => {
              setBasemapFailed(false);
              setReloadKey((k) => k + 1);
            }}
          >
            <RotateCw size={13} />
            Retry
          </Button>
        </div>
      )}

      <div className="absolute bottom-6 left-3 z-20">
        <MapControls />
      </div>
      <LocationHoverCard target={hover} />
    </div>
  );
}
