"use client";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { facesService } from "@/features/faces/api";
import { usePersonRepresentativeFaces } from "@/features/persons/hooks/use-persons";
import { useEventParticipantOptions, useEventPlaceOptions } from "@/features/events/api";
import type { EventLinkPick } from "@/features/events/types";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown, MapPin, Sparkles, TextQuote, Users, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";

interface Row extends EventLinkPick {
  icon: ReactNode;
  personId?: string | null;
  isProvisional?: boolean;
  eventCount?: number;
}

const KIND = {
  participant: { Icon: Users, any: "Anyone", search: "Search people…" },
  place: { Icon: MapPin, any: "Anywhere", search: "Search places…" },
} satisfies Record<string, { Icon: LucideIcon; any: string; search: string }>;

const pickKey = (p: EventLinkPick) => p.id ?? `text:${p.name.toLowerCase()}`;
const textIcon = (
  <TextQuote size={12} aria-label="Unresolved text" className="shrink-0 text-muted-foreground" />
);

/**
 * Who / Where multi-select for the events filter bar. Options are what is
 * actually on events -- linked entities (provisional included) or locations,
 * plus unresolved raw text -- ranked by event count so every pick returns
 * something. Typed text can be added as-is and matches as a substring. Picks
 * OR within one filter; Who and Where AND together.
 */
export function EventLinkFilter({
  kind,
  value = [],
  onChange,
  datasetIds,
}: {
  kind: keyof typeof KIND;
  value?: EventLinkPick[];
  onChange: (next: EventLinkPick[] | undefined) => void;
  datasetIds?: string[];
}) {
  const { Icon, any, search } = KIND[kind];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const q = useDebounce(query, 250).trim() || undefined;

  const participants = useEventParticipantOptions({ datasetIds, q }, open && kind === "participant");
  const places = useEventPlaceOptions({ datasetIds, q }, open && kind === "place");
  const isFetching = participants.isFetching || places.isFetching;

  const rows: Row[] =
    kind === "participant"
      ? (participants.data ?? []).map((o) => {
          const meta = o.entityType ? ENTITY_TYPE_META[o.entityType] : null;
          return {
            id: o.entityId,
            name: o.name,
            personId: o.personId,
            isProvisional: o.isProvisional,
            eventCount: o.eventCount,
            icon: meta ? (
              <meta.Icon size={12} aria-label={meta.label} className={cn("shrink-0", meta.textClass)} />
            ) : (
              textIcon
            ),
          };
        })
      : (places.data ?? []).map((o) => ({
          id: o.locationId,
          name: o.name,
          eventCount: o.eventCount,
          icon: o.locationId ? (
            <MapPin size={12} aria-label="Location" className="shrink-0 text-primary" />
          ) : (
            textIcon
          ),
        }));

  const selected = new Set(value.map(pickKey));
  const toggle = (pick: EventLinkPick) => {
    const next = selected.has(pickKey(pick))
      ? value.filter((p) => pickKey(p) !== pickKey(pick))
      : [...value, { id: pick.id, name: pick.name }];
    onChange(next.length ? next : undefined);
  };
  const typed = query.trim();
  const shown = new Set(rows.map(pickKey));
  const offList = value.filter((p) => !shown.has(pickKey(p)));

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="h-8 w-44 justify-between border-input bg-muted/40 px-2.5 text-xs font-normal hover:bg-muted/60"
        >
          <span className="flex min-w-0 items-center gap-1.5">
            <Icon size={12} className="shrink-0 text-muted-foreground" />
            {value.length ? (
              <span className="truncate text-foreground">
                {value[0].name}
                {value.length > 1 && <span className="text-muted-foreground"> +{value.length - 1}</span>}
              </span>
            ) : (
              <span className="text-muted-foreground">{any}</span>
            )}
          </span>
          <ChevronsUpDown className="size-3 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 border-border bg-popover p-0">
        <Command shouldFilter={false}>
          <CommandInput placeholder={search} value={query} onValueChange={setQuery} className="text-xs" />
          <CommandList>
            {typed && !selected.has(pickKey({ id: null, name: typed })) && (
              <CommandGroup>
                <CommandItem
                  value={`text:${typed}`}
                  onSelect={() => {
                    toggle({ id: null, name: typed });
                    setQuery("");
                  }}
                  className="gap-2 text-xs"
                >
                  {textIcon}
                  <span className="flex-1 truncate">
                    Contains <span className="font-medium text-foreground">“{typed}”</span>
                  </span>
                </CommandItem>
              </CommandGroup>
            )}
            <CommandGroup>
              {offList.map((p) => (
                <OptionRow
                  key={pickKey(p)}
                  row={{ ...p, icon: p.id ? <Icon size={12} className="shrink-0 text-primary" /> : textIcon }}
                  isSelected
                  onSelect={() => toggle(p)}
                />
              ))}
              {rows.map((r) => (
                <OptionRow key={pickKey(r)} row={r} isSelected={selected.has(pickKey(r))} onSelect={() => toggle(r)} />
              ))}
              {!isFetching && rows.length === 0 && offList.length === 0 && (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  {typed ? "No matches on events" : "Nothing linked to events yet"}
                </p>
              )}
            </CommandGroup>
          </CommandList>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
            <span>Ranked by events</span>
            {kind === "participant" && (
              <span className="flex items-center gap-1">
                <Sparkles size={11} className="text-annotation" /> auto-created
              </span>
            )}
            <span className="flex items-center gap-1">
              <TextQuote size={11} /> unresolved text
            </span>
          </p>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function OptionRow({ row, isSelected, onSelect }: { row: Row; isSelected: boolean; onSelect: () => void }) {
  return (
    <CommandItem value={pickKey(row)} onSelect={onSelect} className="gap-2 text-xs">
      <Check className={cn("size-3 shrink-0", isSelected ? "opacity-100" : "opacity-0")} />
      {row.personId ? <PersonAvatar personId={row.personId} fallback={row.icon} /> : row.icon}
      <span className="flex-1 truncate">{row.name}</span>
      {row.isProvisional && (
        <Sparkles size={11} aria-label="Auto-created" className="shrink-0 text-annotation" />
      )}
      {row.eventCount != null && (
        <span className="text-[11px] tabular-nums text-muted-foreground" title="Events">
          {row.eventCount.toLocaleString()}
        </span>
      )}
    </CommandItem>
  );
}

/** A real person's representative face, else the entity-type icon. */
function PersonAvatar({ personId, fallback }: { personId: string; fallback: ReactNode }) {
  const { data: faces } = usePersonRepresentativeFaces(personId);
  const face = faces?.[0];
  if (!face) return fallback;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- tiny same-origin avatar, server already crops/downscales
    <img
      src={facesService.getFaceThumbnailUrl(face.id)}
      alt=""
      className="size-5 shrink-0 rounded-full object-cover"
    />
  );
}
