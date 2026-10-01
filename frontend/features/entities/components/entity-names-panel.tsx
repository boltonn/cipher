"use client";

import { Button } from "@/components/ui/button";
import { useEntityNames, useUpdateEntity } from "@/features/entities/hooks/use-entities";
import { useUnresolveName } from "@/features/entities/hooks/use-entity-matches";
import type { Entity } from "@/features/entities/types";
import { Check, Plus, Undo2 } from "lucide-react";
import { mentionSearchHref } from "@/features/search/links";
import Link from "next/link";

/**
 * The names the evidence uses for an entity -- every resolved name group -- next to its
 * curated aliases. Resolving a name points its mentions here but doesn't make it an alias:
 * a typo ("Nick BI"), a bare surname, or "friend" can resolve to Nick without being his
 * name. Add only the real alternate names as aliases. Each name links to its hits in search;
 * Unresolve sends a wrong one back to the Resolve queue.
 */
export function EntityNamesPanel({ entity }: { entity: Entity }) {
  const { data: names } = useEntityNames(entity.id);
  const update = useUpdateEntity(entity.id);
  const unresolve = useUnresolveName(entity.id);
  const aliases = entity.aliases ?? [];

  if (!names?.length) {
    return <p className="text-xs italic text-muted-foreground">No names resolved to this entity yet.</p>;
  }

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-muted-foreground">
        How the evidence refers to {entity.displayName}. Resolving a name points its mentions here; it doesn&apos;t
        make it an alias. Add real alternate names (a full name, a nickname) — not typos, a bare surname, or
        greetings. Click a name to review its hits; <b>Unresolve</b> sends a wrong one back to the Resolve queue.
      </p>
      <ul className="divide-y divide-border/60 rounded-lg border border-border">
        {names.map((name) => (
          <li key={name.normalizedValue} className="flex items-center gap-3 px-3 py-1.5 text-xs">
            <Link
              href={mentionSearchHref(name.normalizedValue, entity.datasetId)}
              className="min-w-0 flex-1 truncate font-medium text-foreground hover:text-primary hover:underline"
              title={`Review "${name.surface}" in the evidence`}
            >
              {name.surface}
            </Link>
            <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
              {name.mentionCount.toLocaleString()} mention{name.mentionCount === 1 ? "" : "s"}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={unresolve.isPending}
              className="h-6 shrink-0 gap-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
              onClick={() => unresolve.mutate(name.normalizedValue)}
              title="Detach these mentions and send the name back to the Resolve queue"
            >
              <Undo2 size={11} /> Unresolve
            </Button>
            {name.isAlias ? (
              <span className="inline-flex w-28 shrink-0 items-center justify-end gap-1 text-[11px] text-muted-foreground">
                <Check size={11} /> Alias
              </span>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                disabled={update.isPending}
                className="h-6 w-28 shrink-0 justify-end gap-1 px-2 text-[11px]"
                onClick={() => update.mutate({ aliases: [...aliases, name.surface] })}
              >
                <Plus size={11} /> Add as alias
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
