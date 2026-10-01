"use client";

import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  ENTITY_TYPE_META,
  SELECTOR_TYPE_META,
} from "@/features/entities/components/entity-type-meta";
import { SelectorMentions } from "@/features/entities/components/selector-mentions";
import { useDetachSelector } from "@/features/entities/hooks/use-entities";
import type { EntitySummary, SelectorMention } from "@/features/entities/types";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  Quote,
  Search,
  Unlink,
} from "lucide-react";
import { mentionSearchHref } from "@/features/search/links";
import Link from "next/link";
import { useState } from "react";

interface EntitySelectorsProps {
  /** Owning entity (person bridge id works too). */
  entityId: string;
  selectors: EntitySummary[];
  /** Per-selector normalized value + how many mentions carry it. */
  selectorMentions: SelectorMention[];
  /**
   * Whether the mention count expands to an inline by-file preview list. Off for
   * the person dossier, where that nested dropdown reads as clutter -- instead
   * the counts become links out to the selector's page and to search.
   */
  showMentionPreviews?: boolean;
}

const linkChip =
  "inline-flex items-center gap-1 rounded-md border border-primary/25 bg-primary/5 px-1.5 py-0.5 text-[11px] font-semibold text-primary transition-colors hover:border-primary/50 hover:bg-primary/15";

/** Type-aware links out, replacing the inline dropdown on the person dossier. */
function SelectorLinks({
  selectorEntityId,
  match,
}: {
  selectorEntityId: string;
  match?: SelectorMention;
}) {
  const value = match?.normalizedValue ?? "";
  const isEmail = match?.selectorType === "email";
  const sent = match?.sentCount ?? 0;
  const received = match?.receivedCount ?? 0;
  const ner = match?.textCount ?? 0;
  const plain = match?.patternCount ?? 0;
  const total = match?.mentionCount ?? 0;
  const selectorHref = `/entities/${selectorEntityId}`;
  const searchHref = mentionSearchHref(value);

  const chips: React.ReactNode[] = [];
  if (isEmail && (sent > 0 || received > 0)) {
    chips.push(
      <Link key="sent" href={selectorHref} className={linkChip}>
        <ArrowUpRight size={11} />
        {sent} sent
      </Link>,
      <Link key="received" href={selectorHref} className={linkChip}>
        <ArrowDownLeft size={11} />
        {received} received
      </Link>
    );
  }
  if (plain > 0 && value) {
    chips.push(
      <Link key="plain" href={searchHref} className={linkChip}>
        <Search size={11} />
        {plain} in text
      </Link>
    );
  }
  if (ner > 0 && value) {
    chips.push(
      <Link key="ner" href={searchHref} className={linkChip}>
        <Search size={11} />
        {ner} via NER
      </Link>
    );
  }
  if (chips.length === 0 && total > 0) {
    chips.push(
      <Link key="all" href={selectorHref} className={linkChip}>
        <Quote size={11} />
        {total} mention{total === 1 ? "" : "s"}
      </Link>
    );
  }
  if (chips.length === 0) return null;

  return (
    <span className="flex flex-wrap items-center justify-end gap-1">{chips}</span>
  );
}

export function EntitySelectors({
  entityId,
  selectors,
  selectorMentions,
  showMentionPreviews = true,
}: EntitySelectorsProps) {
  const detach = useDetachSelector(entityId);
  const matchByEntity = new Map(selectorMentions.map((m) => [m.entityId, m]));
  const [expanded, setExpanded] = useState<string | null>(null);

  if (selectors.length === 0) {
    return (
      <p className="text-[11px] italic text-muted-foreground">
        No selectors yet. Add a phone, email, or handle to tie this person
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
        const isOpen = showMentionPreviews && expanded === s.id;
        const KindIcon =
          (match?.selectorType && SELECTOR_TYPE_META[match.selectorType]?.Icon) ||
          meta.Icon;
        return (
          <li
            key={s.id}
            className={`overflow-hidden rounded-lg border ${meta.borderClass} ${meta.bgClass}`}
          >
            <div className="flex items-center gap-2 px-2.5 py-1.5">
              <KindIcon size={13} className={`shrink-0 ${meta.textClass}`} />
              <Link
                href={`/entities/${s.id}`}
                className={`font-mono text-xs hover:brightness-125 ${meta.textClass}`}
              >
                {s.displayName}
              </Link>

              <div className="ml-auto flex items-center gap-1">
                {showMentionPreviews ? (
                  <button
                    type="button"
                    disabled={!count}
                    onClick={() => setExpanded(isOpen ? null : s.id)}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 disabled:hover:text-muted-foreground"
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
                ) : (
                  <SelectorLinks selectorEntityId={s.id} match={match} />
                )}

                <ConfirmDialog
                  trigger={
                    <button
                      type="button"
                      aria-label={`Remove ${s.displayName}`}
                      disabled={detach.isPending}
                      className="rounded p-1 text-muted-foreground opacity-60 transition-opacity hover:bg-black/20 hover:text-foreground hover:opacity-100 disabled:opacity-20"
                    >
                      <Unlink size={12} />
                    </button>
                  }
                  title="Remove this selector?"
                  description={
                    <>
                      This removes the relationship between{" "}
                      <span className="font-medium text-foreground">
                        {s.displayName}
                      </span>{" "}
                      and this person. The selector and its mentions are kept —
                      only the relationship is removed.
                    </>
                  }
                  confirmLabel="Remove"
                  isPending={detach.isPending}
                  onConfirm={() => detach.mutate(s.id)}
                />
              </div>
            </div>

            {isOpen && (
              <div className="border-t border-border bg-background/60 px-2.5 py-2">
                <SelectorMentions
                  normalizedValue={match?.normalizedValue ?? null}
                  selectorType={match?.selectorType}
                />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
