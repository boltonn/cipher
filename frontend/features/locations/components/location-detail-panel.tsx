"use client";

import { Button } from "@/components/ui/button";
import { filesService, useFile } from "@/features/files/api";
import { FileViewerDialog } from "@/features/files/components/file-viewer-dialog";
import type { FileBrowserItem } from "@/features/files/types";
import { MarkerIcon } from "@/features/locations/lib/category-icons";
import { colorForValue, type MarkerPalette } from "@/features/locations/lib/marker-style";
import type { LocationProperties } from "@/features/locations/types";
import { format } from "date-fns";
import { ExternalLink, Maximize2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const prettify = (v: string) => v.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex justify-between gap-3 py-1.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium tabular-nums">{value}</span>
    </div>
  );
}

export type SelectedLocation = LocationProperties & { lng: number; lat: number };

export function LocationDetailPanel({
  feature,
  palette,
  onClose,
}: {
  feature: SelectedLocation | null;
  palette: MarkerPalette;
  onClose: () => void;
}) {
  const [viewerOpen, setViewerOpen] = useState(false);
  const { data: file } = useFile(viewerOpen ? (feature?.fileId ?? undefined) : undefined);

  if (!feature) return null;

  const when = feature.dateRecorded ? format(new Date(feature.dateRecorded), "PPpp") : null;
  const preview = feature.fileId ? filesService.getPreviewUrl(feature.fileId, 1200) : null;
  const num = (v: number | null | undefined) => (v === null || v === undefined ? null : Number(v));
  const bearing = num(feature.bearing);
  const velocity = num(feature.velocity);
  const altitude = num(feature.altitude);
  const browserFile: FileBrowserItem | null = file ? { ...file, type: "file" } : null;

  return (
    <>
      <aside className="absolute right-0 top-0 z-30 flex h-full w-96 max-w-[90vw] flex-col border-l bg-popover text-popover-foreground shadow-2xl">
        <div className="flex items-start justify-between gap-2 border-b px-4 py-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
              Location
            </p>
            <p className="flex items-center gap-2 truncate text-sm font-semibold">
              <MarkerIcon
                field="source"
                value={feature.source}
                className="size-4 shrink-0"
                style={{ color: colorForValue(palette, "source", feature.source) }}
              />
              {feature.name ?? "Photo location"}
            </p>
          </div>
          <Button variant="ghost" size="icon" className="size-7 shrink-0" onClick={onClose} aria-label="Close">
            <X className="size-4" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {preview && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="" className="max-h-72 w-full bg-muted object-contain" />
          )}
          <div className="space-y-0.5 p-4">
            <Row label="Source" value={prettify(feature.source)} />
            <Row label="Category" value={feature.category ? prettify(feature.category) : null} />
            <Row label="When" value={when} />
            <Row label="Coordinates" value={`${feature.lat.toFixed(5)}, ${feature.lng.toFixed(5)}`} />
            <Row label="Bearing" value={bearing !== null ? `${bearing}°` : null} />
            <Row label="Speed" value={velocity !== null ? `${velocity.toFixed(2)} m/s` : null} />
            <Row label="Altitude" value={altitude !== null ? `${altitude.toFixed(0)} m` : null} />
          </div>
        </div>

        <div className="flex gap-2 border-t p-3">
          {feature.fileId && (
            <Button variant="default" size="sm" className="flex-1" onClick={() => setViewerOpen(true)}>
              <Maximize2 className="size-3.5" /> Open file viewer
            </Button>
          )}
          {feature.imageId && (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/images?id=${feature.imageId}`}>
                <ExternalLink className="size-3.5" /> Similar
              </Link>
            </Button>
          )}
        </div>
      </aside>

      {browserFile && (
        <FileViewerDialog file={browserFile} isOpen={viewerOpen} onOpenChange={setViewerOpen} />
      )}
    </>
  );
}
