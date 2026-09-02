"use client";

import { LocationHoverCard, type HoverTarget } from "@/features/locations/components/location-hover-card";
import type { SelectedLocation } from "@/features/locations/components/location-detail-panel";
import { MapControls } from "@/features/locations/components/map-controls";
import { withMarkerColor, type MarkerPalette } from "@/features/locations/lib/marker-style";
import { mapStyle, useMapStyleStore } from "@/features/locations/style-store";
import type { BBox, LocationFeature } from "@/features/locations/types";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

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
  const [hover, setHover] = useState<HoverTarget | null>(null);

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

    const map = new maplibregl.Map({
      container,
      style: mapStyle(useMapStyleStore.getState().styleId),
      center: [0, 20],
      zoom: 1.6,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

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
          "circle-opacity": 0.22,
          "circle-radius": ["step", ["get", "point_count"], 16, 25, 22, 100, 30],
        },
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "locations",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
        paint: { "text-color": p.clusterText },
      });
      map.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: "locations",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": ["coalesce", ["get", "markerColor"], paletteRef.current.fallback],
          "circle-radius": 7,
          "circle-stroke-width": 2,
          "circle-stroke-color": paletteRef.current.pointStroke,
        },
      });
    };

    const emitBounds = () => onBoundsChangeRef.current(boundsToBBox(map));

    // Bounds -> parent drives the data fetch. Don't gate it on `load` (a slow
    // vector style can delay or swallow that); fire on move and whenever the
    // style becomes ready.
    map.on("moveend", emitBounds);
    map.on("load", () => {
      addLocationLayers();
      emitBounds();
    });
    map.on("styledata", () => {
      if (!map.isStyleLoaded()) return;
      if (!map.getSource("locations")) addLocationLayers();
      emitBounds();
    });

    map.on("click", "clusters", (e) => {
      const feat = map.queryRenderedFeatures(e.point, { layers: ["clusters"] })[0];
      const source = map.getSource("locations") as maplibregl.GeoJSONSource;
      source.getClusterExpansionZoom(feat.properties?.cluster_id).then((zoom) => {
        map.easeTo({ center: (feat.geometry as GeoJSON.Point).coordinates as [number, number], zoom });
      });
    });
    map.on("mousemove", "unclustered-point", (e) => {
      map.getCanvas().style.cursor = "pointer";
      const feat = e.features?.[0];
      if (!feat) return;
      setHover({ props: feat.properties as unknown as HoverTarget["props"], x: e.point.x, y: e.point.y });
    });
    map.on("mouseleave", "unclustered-point", () => {
      map.getCanvas().style.cursor = "";
      setHover(null);
    });
    map.on("click", "unclustered-point", (e) => {
      const feat = e.features?.[0];
      if (!feat) return;
      const [lng, lat] = (feat.geometry as GeoJSON.Point).coordinates as [number, number];
      onSelectRef.current({ ...(feat.properties as unknown as SelectedLocation), lng, lat });
    });

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // --- basemap style switch (skip the initial mount: the constructor already
  // set the style, and calling setStyle again mid-load wedges the render loop) ---
  const didMountStyleRef = useRef(false);
  useEffect(() => {
    if (!didMountStyleRef.current) {
      didMountStyleRef.current = true;
      return;
    }
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
      map.setPaintProperty("cluster-count", "text-color", palette.clusterText);
      map.setPaintProperty("unclustered-point", "circle-stroke-color", palette.pointStroke);
    }

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
      <div className="absolute bottom-6 left-3 z-20">
        <MapControls />
      </div>
      <LocationHoverCard target={hover} />
    </div>
  );
}
