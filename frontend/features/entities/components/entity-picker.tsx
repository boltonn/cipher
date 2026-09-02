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
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";

interface EntityPickerProps {
  value?: string;
  valueName?: string;
  onSelect: (entityId: string, displayName?: string) => void;
  /** Restrict results to these entity types (e.g. ["organization"]). Empty = any. */
  entityTypes?: EntityType[];
  placeholder?: string;
  className?: string;
}

/** Type-ahead picker over the entity graph, backed by `GET /entities`. */
export function EntityPicker({
  value,
  valueName,
  onSelect,
  entityTypes = [],
  placeholder = "Search entities…",
  className,
}: EntityPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const singleType = entityTypes.length === 1 ? entityTypes[0] : undefined;
  const { data, isFetching } = useEntityList({
    query: query || undefined,
    entityType: singleType,
    limit: 20,
    page: 1,
  });

  const allow = new Set(entityTypes);
  const entities = (data?.data ?? []).filter(
    (e) => allow.size === 0 || allow.has(e.entityType)
  );

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
            {!isFetching && entities.length === 0 && (
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
                    <meta.Icon size={12} className={cn("shrink-0", meta.textClass)} />
                    <span className="flex-1 truncate">{e.displayName}</span>
                    {allow.size !== 1 && (
                      <span className="text-[10px] uppercase text-muted-foreground">
                        {meta.label}
                      </span>
                    )}
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
