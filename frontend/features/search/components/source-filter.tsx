"use client";

import { Command, CommandGroup, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { Ban, Check, ChevronDown, Database, X } from "lucide-react";
import { useState } from "react";
import { useSourceFacets } from "../hooks/use-source-facets";
import type { SearchFilters, SourceValueCount } from "../types";

type SourceFilterState = "include" | "exclude";

type SourceKind = "messageStates" | "sourceTags";

const EXCLUDE_KEY = { messageStates: "excludeMessageStates", sourceTags: "excludeSourceTags" } as const;

const SOURCE_KINDS: { kind: SourceKind; heading: string }[] = [
  { kind: "messageStates", heading: "Message state" },
  { kind: "sourceTags", heading: "Source tags" },
];

/** How these values got here -- the "how" half of "from the data", shown wherever they are. */
export const SOURCE_ORIGIN =
  "From the data, as exported -- the mail client's own labels (Gmail X-Gmail-Labels, Outlook X-Folder). Not a cipher user's or a model's call.";

const JUNK: { kind: SourceKind; value: string }[] = [
  { kind: "messageStates", value: "spam" },
  { kind: "sourceTags", value: "promotions" },
];

export const sourceLabel = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

function stateOf(filters: SearchFilters, kind: SourceKind, value: string): SourceFilterState | undefined {
  if (filters[kind]?.includes(value)) return "include";
  if (filters[EXCLUDE_KEY[kind]]?.includes(value)) return "exclude";
  return undefined;
}

function withState(
  filters: SearchFilters,
  kind: SourceKind,
  value: string,
  state: SourceFilterState | undefined
): SearchFilters {
  const excludeKey = EXCLUDE_KEY[kind];
  const included = (filters[kind] ?? []).filter((other) => other !== value);
  const excluded = (filters[excludeKey] ?? []).filter((other) => other !== value);
  if (state === "include") included.push(value);
  if (state === "exclude") excluded.push(value);
  return { ...filters, [kind]: included.length ? included : undefined, [excludeKey]: excluded.length ? excluded : undefined };
}

const NEXT_STATE = { off: "include", include: "exclude", exclude: undefined } as const;

function SourceChip({ value, state, onCycle, onRemove }: { value: string; state: SourceFilterState; onCycle: () => void; onRemove: () => void }) {
  const Icon = state === "include" ? Check : Ban;
  return (
    <span className="flex h-7 items-center rounded-md border border-border bg-secondary text-xs font-medium text-secondary-foreground" title={SOURCE_ORIGIN}>
      <button type="button" onClick={onCycle} className="flex h-full items-center gap-1.5 rounded-l-md pl-2 pr-1 hover:bg-foreground/5">
        <Icon className="h-3 w-3 shrink-0" />
        {state === "exclude" ? `Not ${value}` : sourceLabel(value)}
      </button>
      <button type="button" aria-label="Remove filter" onClick={onRemove} className="flex h-full items-center rounded-r-md px-1.5 hover:bg-foreground/5">
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

interface SourceFilterProps {
  filters: SearchFilters;
  onFiltersChange: (filters: SearchFilters) => void;
}

/** Filters on what the data itself says (spam folder, Gmail's promotions tab...): each click cycles only -> hide -> off. */
export function SourceFilter({ filters, onFiltersChange }: SourceFilterProps) {
  const [open, setOpen] = useState(false);
  const { data: facets } = useSourceFacets(filters.datasetId);
  const cycle = (kind: SourceKind, value: string) =>
    onFiltersChange(withState(filters, kind, value, NEXT_STATE[stateOf(filters, kind, value) ?? "off"]));
  const active = SOURCE_KINDS.flatMap(({ kind }) => [
    ...(filters[kind] ?? []).map((value) => ({ kind, value, state: "include" as const })),
    ...(filters[EXCLUDE_KEY[kind]] ?? []).map((value) => ({ kind, value, state: "exclude" as const })),
  ]);
  const available = (kind: SourceKind): SourceValueCount[] => facets?.[kind] ?? [];
  const junk = JUNK.filter(({ kind, value }) => available(kind).some((facet) => facet.value === value));
  const hideJunk = () =>
    onFiltersChange(junk.reduce((next, { kind, value }) => withState(next, kind, value, "exclude"), filters));

  if (!active.length && !SOURCE_KINDS.some(({ kind }) => available(kind).length)) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5" title={SOURCE_ORIGIN}>
      <span className="flex items-center gap-1 pr-0.5 text-[11px] font-medium text-muted-foreground/70">
        <Database className="h-3 w-3" /> From the data
      </span>
      {active.map(({ kind, value, state }) => (
        <SourceChip
          key={`${kind}:${value}`}
          value={value}
          state={state}
          onCycle={() => cycle(kind, value)}
          onRemove={() => onFiltersChange(withState(filters, kind, value, undefined))}
        />
      ))}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger className="flex h-7 items-center gap-1 rounded-md border border-border px-2 text-xs text-muted-foreground hover:text-foreground">
          {active.length ? "More…" : "Any"}
          <ChevronDown className="h-3 w-3 opacity-60" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72 p-0">
          <p className="border-b border-border px-3 py-2 text-[11px] text-muted-foreground">
            {SOURCE_ORIGIN} Click to cycle: only → hide → off.
          </p>
          <Command>
            <CommandList>
              {junk.length > 0 && (
                <CommandGroup>
                  <CommandItem onSelect={hideJunk} className="gap-2 text-xs">
                    <Ban className="h-3 w-3 shrink-0" />
                    Hide {junk.map(({ value }) => value).join(" & ")}
                  </CommandItem>
                </CommandGroup>
              )}
              {SOURCE_KINDS.map(({ kind, heading }) =>
                available(kind).length ? (
                  <CommandGroup key={kind} heading={heading}>
                    {available(kind).map(({ value, fileCount }) => {
                      const state = stateOf(filters, kind, value);
                      const Icon = state === "exclude" ? Ban : Check;
                      return (
                        <CommandItem key={value} value={`${kind}:${value}`} onSelect={() => cycle(kind, value)} className="gap-2 text-xs">
                          <span
                            className={cn(
                              "flex size-4 shrink-0 items-center justify-center rounded border",
                              state ? "border-foreground/30 bg-secondary text-secondary-foreground" : "border-border text-transparent"
                            )}
                          >
                            <Icon className="size-3" />
                          </span>
                          <span className="flex-1 truncate">{sourceLabel(value)}</span>
                          <span className="text-[11px] tabular-nums text-muted-foreground">{fileCount.toLocaleString()}</span>
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                ) : null
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
