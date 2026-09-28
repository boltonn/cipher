"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { useEnrichmentEstimates } from "@/features/datasets/api";
import { EstimateBadge } from "@/features/datasets/components/estimate-badge";
import { formatDuration } from "@/features/datasets/request-types";
import { formatCompactNumber } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import {
  Binary,
  CalendarClock,
  Contact,
  FileText,
  Gauge,
  Image as ImageIcon,
  Info,
  KeyRound,
  Loader2,
  MapPin,
  Network,
  ScanFace,
  ScanText,
  Timer,
  Users,
  UsersRound,
  Waypoints,
} from "lucide-react";
import { useState } from "react";

const META: Record<string, { label: string; Icon: IconComponent }> = {
  text_extraction: { label: "Text extraction", Icon: FileText },
  ocr: { label: "OCR", Icon: ScanText },
  text_embedding: { label: "Text embedding", Icon: Binary },
  image_embedding: { label: "Image embedding", Icon: ImageIcon },
  exif_location: { label: "Photo locations", Icon: MapPin },
  face_detection: { label: "Face detection", Icon: ScanFace },
  face_matching: { label: "Face matching", Icon: Users },
  face_clustering: { label: "Face clustering", Icon: UsersRound },
  contact_extraction: { label: "Contact extraction", Icon: Contact },
  selector_extraction: { label: "Selector extraction", Icon: KeyRound },
  entity_extraction: { label: "Entity extraction", Icon: Network },
  relationship_extraction: {
    label: "Relationship extraction",
    Icon: Waypoints,
  },
  event_extraction: { label: "Event extraction", Icon: CalendarClock },
};

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-6 rounded-2xl border border-border bg-muted/40 p-6 backdrop-blur-2xl">
      {children}
    </div>
  );
}

export function EnrichmentEstimates({ datasetId }: { datasetId: string }) {
  const [device, setDevice] = useState<"cpu" | "cuda">("cpu");
  const { data, isPending, isError } = useEnrichmentEstimates(
    datasetId,
    device
  );

  // Older backend without the route -- fail quiet rather than a broken section.
  if (isError) return null;

  const header = (
    <div className="mb-4 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Timer size={14} className="text-primary" />
        <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
          Enrichment Estimates
        </h2>
      </div>
      <ButtonGroup>
        {(["cpu", "cuda"] as const).map((d) => (
          <Button
            key={d}
            type="button"
            size="sm"
            variant={device === d ? "default" : "outline"}
            onClick={() => setDevice(d)}
            className="h-7"
          >
            {d === "cpu" ? "CPU" : "GPU"}
          </Button>
        ))}
      </ButtonGroup>
    </div>
  );

  if (isPending) {
    return (
      <Card>
        {header}
        <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Estimating…
        </div>
      </Card>
    );
  }

  if (!data || data.items.length === 0) return null;

  const remaining = data.items
    .filter((it) => it.progress < 0.999 && it.estimateSeconds != null)
    .reduce((sum, it) => sum + (it.estimateSeconds ?? 0), 0);
  const hasRemaining = data.items.some(
    (it) => it.progress < 0.999 && it.estimateSeconds != null
  );

  return (
    <Card>
      {header}

      {!data.isStaged ? (
        <Alert>
          <Info />
          <AlertDescription>
            This dataset isn&apos;t staged yet (no files loaded &amp; typed).
            Estimates appear once it is.
          </AlertDescription>
        </Alert>
      ) : (
        <ul className="divide-y divide-border/60">
          {data.items.map((item) => {
            const meta = META[item.enrichmentType] ?? {
              label: item.enrichmentType.replace(/_/g, " "),
              Icon: Gauge,
            };
            const pct = Math.round(item.progress * 100);
            const inFlight = item.progress > 0.001 && item.progress < 0.999;

            return (
              <li
                key={item.enrichmentType}
                className="flex items-center justify-between gap-3 py-2"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <meta.Icon className="size-3 shrink-0 text-muted-foreground" />
                  <span className="truncate text-sm text-foreground">
                    {meta.label}
                  </span>
                  {item.eligible.estimable && item.eligible.unitCount > 0 && (
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {formatCompactNumber(item.eligible.unitCount)}{" "}
                      {item.eligible.unit.replace(/_/g, " ")}
                    </span>
                  )}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {inFlight && (
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {pct}%
                    </span>
                  )}
                  <EstimateBadge estimate={item} />
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {data.isStaged && hasRemaining && (
        <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-3 text-sm">
          <span className="text-muted-foreground">
            Remaining to run{" "}
            <span className="text-muted-foreground/60">
              ({device.toUpperCase()}, sequential)
            </span>
          </span>
          <span className="font-medium tabular-nums text-foreground">
            {formatDuration(remaining)}
          </span>
        </div>
      )}
    </Card>
  );
}
