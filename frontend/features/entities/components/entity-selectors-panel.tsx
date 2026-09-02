"use client";

import { Button } from "@/components/ui/button";
import { EntitySelectors } from "@/features/entities/components/entity-selectors";
import { useEntityRelatedInfinite } from "@/features/entities/hooks/use-entities";
import type { EntitySummary, SelectorMention } from "@/features/entities/types";
import { Loader2 } from "lucide-react";
import { useMemo } from "react";

/**
 * Paged wrapper around <EntitySelectors> for the entity dossier: pulls linked
 * selectors from GET /entities/{id}/related?entity_type=selector so a hub with
 * hundreds of them isn't dumped at once.
 */
export function EntitySelectorsPanel({ entityId }: { entityId: string }) {
  const { data, isPending, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useEntityRelatedInfinite(entityId, {
      entityType: "selector",
      sort: "name",
    });

  const rows = useMemo(
    () => data?.pages.flatMap((p) => p.data) ?? [],
    [data]
  );
  const total = data?.pages[0]?.total ?? 0;

  const selectors: EntitySummary[] = rows.map((r) => r.entity);
  const selectorMentions: SelectorMention[] = rows.map((r) => ({
    entityId: r.entity.id,
    selectorKind: r.selectorKind ?? null,
    normalizedValue: r.normalizedValue ?? null,
    mentionCount: r.mentionCount ?? 0,
  }));

  if (isPending) {
    return <Loader2 size={16} className="animate-spin text-muted-foreground" />;
  }

  return (
    <div className="space-y-3">
      {total > 0 && (
        <p className="text-[11px] text-muted-foreground">
          Showing {rows.length} of {total}
        </p>
      )}
      <EntitySelectors
        entityId={entityId}
        selectors={selectors}
        selectorMentions={selectorMentions}
      />
      {hasNextPage && (
        <div className="flex justify-center">
          <Button
            variant="ghost"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="text-[10px] uppercase tracking-widest text-primary"
          >
            {isFetchingNextPage && (
              <Loader2 size={12} className="mr-2 animate-spin" />
            )}
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
