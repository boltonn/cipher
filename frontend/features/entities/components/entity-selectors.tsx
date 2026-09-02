"use client";

import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { SelectorMentions } from "@/features/entities/components/selector-mentions";
import { useDetachSelector } from "@/features/entities/hooks/use-entities";
import type { EntitySummary, SelectorMention } from "@/features/entities/types";
import { ChevronDown, Quote, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

interface EntitySelectorsProps {
  /** Owning entity (person bridge id works too). */
  entityId: string;
  selectors: EntitySummary[];
  /** Per-selector normalized value + how many mentions carry it. */
  selectorMentions: SelectorMention[];
}

export function EntitySelectors({
  entityId,
  selectors,
  selectorMentions,
}: EntitySelectorsProps) {
  const detach = useDetachSelector(entityId);
  const matchByEntity = new Map(selectorMentions.map((m) => [m.entityId, m]));
  const [expanded, setExpanded] = useState<string | null>(null);

  if (selectors.length === 0) {
    return (
      <p className="text-[11px] italic text-muted-foreground">
        No selectors linked yet. Add a phone, email, or handle to tie this person
        to communications and records.
      </p>
    );
  }

  const meta = ENTITY_TYPE_META.selector;

  return (
    <ul className="space-y-2">
      {selectors.map((s) => {
        const match = matchByEntity.get(s.id);
        const count = match?.mentionCount ?? 0;
        const isOpen = expanded === s.id;
        return (
          <li
            key={s.id}
            className={`overflow-hidden rounded-lg border ${meta.borderClass} ${meta.bgClass}`}
          >
            <div className="flex items-center gap-2 px-2.5 py-1.5">
              <Link
                href={`/entities/${s.id}`}
                className={`font-mono text-xs hover:brightness-125 ${meta.textClass}`}
              >
                {s.displayName}
              </Link>

              <button
                type="button"
                disabled={!count}
                onClick={() => setExpanded(isOpen ? null : s.id)}
                className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 disabled:hover:text-muted-foreground"
                aria-expanded={isOpen}
              >
                <Quote size={11} />
                {count} mention{count === 1 ? "" : "s"}
                {count > 0 && (
                  <ChevronDown
                    size={12}
                    className={`transition-transform ${isOpen ? "rotate-180" : ""}`}
                  />
                )}
              </button>

              <button
                type="button"
                aria-label={`Unlink ${s.displayName}`}
                disabled={detach.isPending}
                onClick={() => detach.mutate(s.id)}
                className="rounded p-0.5 text-muted-foreground opacity-50 transition-opacity hover:bg-black/20 hover:text-foreground hover:opacity-100 disabled:opacity-20"
              >
                <X size={12} />
              </button>
            </div>

            {isOpen && (
              <div className="border-t border-border bg-background/60 px-2.5 py-2">
                <SelectorMentions
                  normalizedValue={match?.normalizedValue ?? null}
                  selectorKind={match?.selectorKind}
                />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
