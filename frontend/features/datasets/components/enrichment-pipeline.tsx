"use client";

import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperSeparator,
  StepperTitle,
} from "@/components/ui/stepper";
import { Button } from "@/components/ui/button";
import { useEnrichmentProgress, useRunEnrichment } from "@/features/datasets/api";
import { EnrichmentFailuresDialog } from "@/features/datasets/components/enrichment-failures-dialog";
import type { EnrichmentProgress } from "@/features/datasets/types";
import { formatCompactNumber } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import {
  Binary,
  FileText,
  Image as ImageIcon,
  KeyRound,
  ListChecks,
  Loader2,
  MapPin,
  Network,
  ScanFace,
  Users,
  Waypoints,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

const META: Record<string, { label: string; Icon: IconComponent }> = {
  text_extraction: { label: "Text extraction", Icon: FileText },
  text_embedding: { label: "Text embedding", Icon: Binary },
  image_embedding: { label: "Image embedding", Icon: ImageIcon },
  exif_location: { label: "Photo locations", Icon: MapPin },
  face_detection: { label: "Face detection", Icon: ScanFace },
  face_matching: { label: "Face matching", Icon: Users },
  selector_extraction: { label: "Selector extraction", Icon: KeyRound },
  entity_extraction: { label: "Entity extraction", Icon: Network },
  relationship_extraction: { label: "Relationship extraction", Icon: Waypoints },
};

type StepState = "done" | "failed" | "running";

function deriveState(p: EnrichmentProgress): StepState {
  const outstanding = (p.counts.pending ?? 0) + (p.counts.processing ?? 0);
  if (outstanding > 0) return "running";
  // A step only reads as "failed" when nothing got through. A handful of bad
  // rows among many good ones is still a completed step -- surfaced via the
  // failed count and the red segment in the bar, not the whole step.
  if ((p.counts.failed ?? 0) > 0 && p.completed === 0) return "failed";
  return "done";
}

function Card({ action, children }: { action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mt-6 rounded-2xl border border-border bg-muted/40 p-6 backdrop-blur-2xl">
      <div className="mb-4 flex items-center justify-between gap-2 text-muted-foreground">
        <div className="flex items-center gap-2">
          <ListChecks size={14} className="text-primary" />
          <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
            Enrichment Pipeline
          </h2>
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function RunExifLocationsButton({ datasetId }: { datasetId: string }) {
  const { mutate, isPending } = useRunEnrichment(datasetId);
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={isPending}
      onClick={() =>
        mutate("exif_location", {
          onSuccess: (r) => toast.success(r.detail),
        })
      }
    >
      <MapPin className="size-3.5" />
      {isPending ? "Starting…" : "Extract photo locations"}
    </Button>
  );
}

export function EnrichmentPipeline({ datasetId }: { datasetId: string }) {
  const { data, isPending, isError } = useEnrichmentProgress(datasetId);
  const [activeType, setActiveType] = useState<string | null>(null);

  // The route may be unavailable (older backend) -- fail quiet rather than
  // showing a broken section.
  if (isError) return null;

  const runButton = <RunExifLocationsButton datasetId={datasetId} />;

  if (isPending) {
    return (
      <Card action={runButton}>
        <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading pipeline…
        </div>
      </Card>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card action={runButton}>
        <p className="py-2 text-xs text-muted-foreground">
          No analytics have run against this dataset yet.
        </p>
      </Card>
    );
  }

  return (
    <Card action={runButton}>
      <Stepper value={-1} orientation="vertical">
        {data.map((p, index) => {
          const meta = META[p.enrichmentType] ?? {
            label: p.enrichmentType.replace(/_/g, " "),
            Icon: ListChecks,
          };
          const state = deriveState(p);
          const failed = p.counts.failed ?? 0;
          const queued = (p.counts.pending ?? 0) + (p.counts.processing ?? 0);
          const pct = Math.round(p.progress * 100);
          const completedPct = p.total ? (p.completed / p.total) * 100 : 0;
          const failedPct = p.total ? (failed / p.total) * 100 : 0;

          return (
            <StepperItem
              key={p.enrichmentType}
              step={index}
              completed={state === "done"}
              failed={state === "failed"}
              loading={state === "running"}
            >
              <div className="flex gap-3">
                <div className="flex flex-col items-center">
                  <StepperIndicator />
                  {index < data.length - 1 && <StepperSeparator />}
                </div>

                <div className="min-w-0 flex-1 pb-5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <meta.Icon className="size-3 shrink-0 text-muted-foreground" />
                      <StepperTitle className="truncate">{meta.label}</StepperTitle>
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                      {pct}%
                    </span>
                  </div>

                  <div className="mt-1.5 flex h-1 w-full overflow-hidden rounded-full bg-border">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{
                        width: `${p.completed > 0 ? Math.max(completedPct, 2) : 0}%`,
                      }}
                    />
                    <div
                      className="h-full bg-destructive/70 transition-all"
                      style={{
                        width: `${failed > 0 ? Math.max(failedPct, 2) : 0}%`,
                      }}
                    />
                  </div>

                  <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                    <span>{formatCompactNumber(p.completed)} done</span>
                    {failed > 0 && (
                      <button
                        type="button"
                        onClick={() => setActiveType(p.enrichmentType)}
                        className="text-destructive underline-offset-2 hover:underline"
                      >
                        · {formatCompactNumber(failed)} failed
                      </button>
                    )}
                    {queued > 0 && (
                      <span>· {formatCompactNumber(queued)} queued</span>
                    )}
                    <span className="text-muted-foreground/60">
                      · {formatCompactNumber(p.total)} total
                    </span>
                  </p>
                </div>
              </div>
            </StepperItem>
          );
        })}
      </Stepper>

      {activeType && (
        <EnrichmentFailuresDialog
          datasetId={datasetId}
          enrichmentType={activeType}
          label={META[activeType]?.label ?? activeType.replace(/_/g, " ")}
          onClose={() => setActiveType(null)}
        />
      )}
    </Card>
  );
}
