"use client";

import { filesService } from "@/features/files/api";
import type { LocationProperties } from "@/features/locations/types";
import { format } from "date-fns";

export interface HoverTarget {
  props: LocationProperties;
  x: number;
  y: number;
}

/** Lightweight, non-interactive preview shown while a point is hovered. Click opens the panel. */
export function LocationHoverCard({ target }: { target: HoverTarget | null }) {
  if (!target) return null;
  const { props, x, y } = target;
  const when = props.dateRecorded ? format(new Date(props.dateRecorded), "PP p") : "Time unknown";
  const thumb = props.fileId ? filesService.getPreviewUrl(props.fileId, 480) : null;

  return (
    <div
      className="pointer-events-none absolute z-20 w-52 -translate-x-1/2 -translate-y-[calc(100%+14px)] overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-lg"
      style={{ left: x, top: y }}
    >
      {thumb && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={thumb} alt="" className="h-28 w-full object-cover" />
      )}
      <div className="space-y-0.5 p-2.5">
        <p className="truncate text-sm font-medium">{props.name ?? "Photo location"}</p>
        <p className="text-xs text-muted-foreground">{when}</p>
        <p className="text-xs text-muted-foreground">Click for details</p>
      </div>
    </div>
  );
}
