"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EntityPicker } from "@/features/entities/components/entity-picker";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { InvalidateEntityDialog } from "@/features/entities/components/invalidate-entity-dialog";
import { useEntity } from "@/features/entities/hooks/use-entities";
import { SELECTOR_TYPE_LABELS } from "@/features/entities/types";
import type { MentionProvenance, SelectorType } from "@/features/entities/types";
import { cn } from "@/lib/utils";
import { Ban, ChevronDown, ExternalLink, FileText, Mail, TextQuote, X } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useState } from "react";
import type { SearchFilters, SearchFiletypeGroup } from "../types";

interface SearchFiltersBarProps {
  filters: SearchFilters;
  onFiltersChange: (filters: SearchFilters) => void;
}

type EntityFilterKey = "entityIds" | "sentFrom" | "sentTo";

const TYPE_OPTIONS: { value: SearchFiletypeGroup | undefined; label: string; Icon?: typeof FileText }[] = [
  { value: undefined, label: "All" },
  { value: "document", label: "Documents", Icon: FileText },
  { value: "email", label: "Emails", Icon: Mail },
];

const ENTITY_FILTERS: { key: EntityFilterKey; label: string; placeholder: string; title: string }[] = [
  { key: "entityIds", label: "Mentions", placeholder: "Entity or text", title: "Files that mention every one of these -- an entity, or a mention value like an IP or a name" },
  { key: "sentFrom", label: "From", placeholder: "Anyone", title: "Emails sent by any of these (person, org or address)" },
  { key: "sentTo", label: "To", placeholder: "Anyone", title: "Emails sent to / cc / bcc any of these" },
];

function FilterGroup({ label, title, children }: { label: string; title?: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" title={title}>
      <span className="pr-0.5 text-[11px] font-medium text-muted-foreground/70">{label}</span>
      {children}
    </div>
  );
}

export function EntityName({ entityId }: { entityId: string }) {
  const { data: entity } = useEntity(entityId);
  return <>{entity?.displayName ?? "…"}</>;
}

/** An entity filter chip; its menu opens the entity or marks it invalid (junk extractions like "1"). */
function EntityChip({ entityId, onRemove }: { entityId: string; onRemove: () => void }) {
  const { data: entity } = useEntity(entityId);
  const [isInvalidateOpen, setInvalidateOpen] = useState(false);
  const meta = entity ? ENTITY_TYPE_META[entity.entityType] : undefined;

  return (
    <span className="flex h-7 items-center rounded-md bg-annotation/10 text-xs font-medium text-annotation">
      <DropdownMenu>
        <DropdownMenuTrigger className="flex h-full items-center gap-1.5 rounded-l-md pl-2 pr-1 hover:bg-annotation/15">
          {meta && <meta.Icon className="h-3 w-3 shrink-0" />}
          {entity?.displayName ?? "Entity"}
          <ChevronDown className="h-3 w-3 opacity-60" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="text-xs">
          <DropdownMenuItem asChild>
            <Link href={`/entities/${entityId}`}>
              <ExternalLink className="h-3.5 w-3.5" /> Open entity
            </Link>
          </DropdownMenuItem>
          {entity && !entity.personId && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={() => setInvalidateOpen(true)}>
                <Ban className="h-3.5 w-3.5" /> Mark invalid…
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <button type="button" aria-label="Remove filter" onClick={onRemove} className="flex h-full items-center rounded-r-md px-1.5 hover:bg-annotation/15">
        <X className="h-3 w-3" />
      </button>
      {entity && (
        <InvalidateEntityDialog entity={entity} open={isInvalidateOpen} onOpenChange={setInvalidateOpen} onDone={onRemove} />
      )}
    </span>
  );
}

const MENTION_WHERE: { key: string; label: string; title: string; provenance?: MentionProvenance[] }[] = [
  { key: "any", label: "Anywhere", title: "Body text, email headers or other metadata" },
  { key: "text", label: "In text", title: "Written in the body", provenance: ["text", "pattern"] },
  { key: "header", label: "In headers", title: "Email From / To / Cc / Bcc", provenance: ["email_header"] },
  { key: "metadata", label: "In metadata", title: "Other structured fields (vCard, document properties)", provenance: ["metadata"] },
];

export function mentionWhere(provenance: MentionProvenance[] | undefined) {
  return MENTION_WHERE.find((w) => w.provenance?.join() === provenance?.join()) ?? MENTION_WHERE[0];
}

/** A mention-value filter chip -- every mention of the value, resolved to an entity or not. */
function MentionValueChip({ value, onRemove }: { value: string; onRemove: () => void }) {
  return (
    <span className="flex h-7 items-center gap-1.5 rounded-md border border-dashed border-annotation/50 bg-annotation/10 pl-2 text-xs font-medium text-annotation">
      <TextQuote className="h-3 w-3 shrink-0" />
      <span className="max-w-40 truncate">“{value}”</span>
      <button type="button" aria-label="Remove filter" onClick={onRemove} className="flex h-full items-center rounded-r-md px-1.5 hover:bg-annotation/15">
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

/** Type, entity-mention, sender/recipient and date filters -- all compose with every search mode (and an empty-query browse). */
export function SearchFiltersBar({ filters, onFiltersChange }: SearchFiltersBarProps) {
  const selectorType = filters.selectorTypes?.[0] as SelectorType | undefined;
  const setIds = (key: EntityFilterKey, next: string[]) =>
    onFiltersChange({ ...filters, [key]: next.length ? next : undefined });
  const mentionValues = filters.mentionValues ?? [];
  const setMentionValues = (next: string[]) =>
    onFiltersChange({
      ...filters,
      mentionValues: next.length ? next : undefined,
      mentionProvenance: next.length ? filters.mentionProvenance : undefined,
    });

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 px-1">
      <FilterGroup label="Type">
        <div className="flex items-center gap-0.5">
          {TYPE_OPTIONS.map(({ value, label, Icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => onFiltersChange({ ...filters, filetypeGroup: value })}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors",
                filters.filetypeGroup === value
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {Icon && <Icon className="h-3 w-3 shrink-0" />}
              {label}
            </button>
          ))}
        </div>
      </FilterGroup>

      {ENTITY_FILTERS.map(({ key, label, placeholder, title }) => {
        const ids = filters[key] ?? [];
        return (
          <FilterGroup key={key} label={label} title={title}>
            {ids.map((id) => (
              <EntityChip key={id} entityId={id} onRemove={() => setIds(key, ids.filter((other) => other !== id))} />
            ))}
            {key === "entityIds" &&
              mentionValues.map((value) => (
                <MentionValueChip
                  key={value}
                  value={value}
                  onRemove={() => setMentionValues(mentionValues.filter((other) => other !== value))}
                />
              ))}
            {key === "entityIds" && mentionValues.length > 0 && (
              <div className="flex items-center gap-0.5">
                {MENTION_WHERE.map((where) => (
                  <button
                    key={where.key}
                    type="button"
                    title={where.title}
                    onClick={() => onFiltersChange({ ...filters, mentionProvenance: where.provenance })}
                    className={cn(
                      "flex h-7 items-center rounded-md px-2 text-xs font-medium transition-colors",
                      mentionWhere(filters.mentionProvenance).key === where.key
                        ? "bg-annotation/10 text-annotation"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {where.label}
                  </button>
                ))}
              </div>
            )}
            <EntityPicker
              datasetId={filters.datasetId}
              placeholder={
                ids.length || (key === "entityIds" && mentionValues.length)
                  ? key === "entityIds"
                    ? "And also…"
                    : "Or…"
                  : placeholder
              }
              className="h-7 w-36"
              onSelect={(id) => !ids.includes(id) && setIds(key, [...ids, id])}
              onSelectText={
                key === "entityIds"
                  ? (text) => !mentionValues.includes(text) && setMentionValues([...mentionValues, text])
                  : undefined
              }
            />
          </FilterGroup>
        );
      })}

      <FilterGroup label="Date">
        <DateRangePicker
          placeholder="Any date"
          className="h-7 w-52"
          value={{ from: filters.dateFrom, to: filters.dateTo }}
          onChange={({ from, to }) => onFiltersChange({ ...filters, dateFrom: from, dateTo: to })}
        />
      </FilterGroup>

      {selectorType && (
        <FilterGroup label="Selector">
          <span className="flex h-7 items-center gap-1.5 rounded-md bg-muted px-2 text-xs font-medium text-muted-foreground">
            {SELECTOR_TYPE_LABELS[selectorType] ?? selectorType}
            <button
              type="button"
              aria-label="Remove filter"
              onClick={() => onFiltersChange({ ...filters, selectorTypes: undefined })}
              className="rounded-sm hover:bg-foreground/10"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        </FilterGroup>
      )}
    </div>
  );
}
