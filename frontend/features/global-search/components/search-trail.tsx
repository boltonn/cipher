"use client";

import { useEntity } from "@/features/entities/hooks/use-entities";
import { format, parseISO } from "date-fns";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import type { OverviewRequest, SearchRecord } from "../types";

function EntityName({ entityId }: { entityId: string }) {
  const { data: entity } = useEntity(entityId);
  return <>{entity?.displayName ?? "an entity"}</>;
}

/** What this step added to the one before it, in a few words. */
function StepLabel({ step, previous }: { step: OverviewRequest; previous?: OverviewRequest }) {
  if (!previous || step.query !== previous.query) return <>{step.query || "Everything"}</>;
  const added = step.filters.entityIds.filter((id) => !previous.filters.entityIds.includes(id));
  if (added.length) return <EntityName entityId={added[0]} />;
  const groups = step.filters.filetypeGroups.filter((group) => !previous.filters.filetypeGroups.includes(group));
  if (groups.length) return <>{groups.join(", ")}</>;
  if (step.filters.dateFrom && step.filters.dateFrom !== previous.filters.dateFrom) {
    const from = format(parseISO(step.filters.dateFrom), "MMM yyyy");
    const to = step.filters.dateTo ? format(parseISO(step.filters.dateTo), "MMM yyyy") : null;
    return <>{to && to !== from ? `${from} – ${to}` : from}</>;
  }
  if (step.datasetIds.join() !== previous.datasetIds.join()) return <>other datasets</>;
  return <>filters changed</>;
}

/** The narrowing steps that led here; click one to jump straight back to it. */
export function SearchTrail({ trail }: { trail: SearchRecord[] }) {
  if (trail.length < 2) return null;
  return (
    <nav aria-label="How you got here" className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
      {trail.map((step, index) => {
        const label = <StepLabel step={step} previous={trail[index - 1]} />;
        const last = index === trail.length - 1;
        return (
          <span key={step.id} className="inline-flex items-center gap-1">
            {index > 0 && <ChevronRight className="size-3.5" />}
            {last ? (
              <span className="font-medium text-foreground">{label}</span>
            ) : (
              <Link href={`/search/${step.id}`} className="hover:text-foreground hover:underline">
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
