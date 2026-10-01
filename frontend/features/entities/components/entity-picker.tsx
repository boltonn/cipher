"use client";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { useEntityList } from "@/features/entities/hooks/use-entities";
import type { EntityType } from "@/features/entities/types";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown, TextQuote } from "lucide-react";
import { useState } from "react";

interface EntityPickerProps {
  value?: string;
  valueName?: string;
  onSelect: (entityId: string, displayName?: string) => void;
  /** Restrict results to these entity types (e.g. ["organization"]). Empty = any. */
  entityTypes?: EntityType[];
  /** Scope results to one dataset (e.g. the search page's active dataset). */
  datasetId?: string;
  placeholder?: string;
  className?: string;
  /** Offer the typed text itself as a pick (e.g. "any mention of …" -- values with no entity). */
  onSelectText?: (text: string) => void;
}

/** Type-ahead picker over the entity graph, backed by `GET /entities`. */
export function EntityPicker({
  value,
  valueName,
  onSelect,
  entityTypes = [],
  datasetId,
  placeholder = "Search entities…",
  className,
  onSelectText,
}: EntityPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 250);

  const singleType = entityTypes.length === 1 ? entityTypes[0] : undefined;
  const { data, isFetching } = useEntityList({
    query: debouncedQuery || undefined,
    entityType: singleType,
    datasetId,
    // typing: best name match first; empty: the most-mentioned entities are the likeliest picks
    sortBy: debouncedQuery ? "relevance" : "mention_count",
    sortOrder: debouncedQuery ? undefined : "desc",
    limit: 20,
    page: 1,
  }, open); // closed pickers (three sit in the search filter bar) shouldn't load on page render

  const allow = new Set(entityTypes);
  const entities = (data?.data ?? []).filter(
    (e) => allow.size === 0 || allow.has(e.entityType)
  );
  const typedText = onSelectText ? query.trim() : "";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "h-10 w-full justify-between border-border bg-muted/40 text-xs hover:bg-muted/60",
            className
          )}
        >
          <span
            className={cn(
              "truncate",
              value ? "text-foreground" : "text-muted-foreground"
            )}
          >
            {valueName ?? value ?? placeholder}
          </span>
          <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 border-border bg-popover p-0">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search…"
            value={query}
            onValueChange={setQuery}
            className="text-xs"
          />
          <CommandList>
            {typedText && (
              <CommandGroup>
                <CommandItem
                  value={`text:${typedText}`}
                  onSelect={() => {
                    onSelectText?.(typedText);
                    setOpen(false);
                    setQuery("");
                  }}
                  className="gap-2 text-xs"
                >
                  <TextQuote size={12} className="shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate">
                    Any mention of <span className="font-medium text-foreground">“{typedText}”</span>
                  </span>
                </CommandItem>
              </CommandGroup>
            )}
            {!isFetching && entities.length === 0 && !typedText && (
              <CommandEmpty className="py-4 text-xs text-muted-foreground">
                {query ? "No match" : "Type to search"}
              </CommandEmpty>
            )}
            <CommandGroup>
              {entities.map((e) => {
                const meta = ENTITY_TYPE_META[e.entityType];
                return (
                  <CommandItem
                    key={e.id}
                    value={e.id}
                    onSelect={() => {
                      onSelect(e.id, e.displayName);
                      setOpen(false);
                      setQuery("");
                    }}
                    className="gap-2 text-xs"
                  >
                    <Check
                      className={cn(
                        "h-3 w-3 shrink-0",
                        value === e.id ? "opacity-100" : "opacity-0"
                      )}
                    />
                    <meta.Icon size={12} aria-label={meta.label} className={cn("shrink-0", meta.textClass)} />
                    <span className="flex-1 truncate">{e.displayName}</span>
                    <span className="text-[11px] tabular-nums text-muted-foreground" title="Mentions">
                      {e.mentionCount.toLocaleString()}
                    </span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
