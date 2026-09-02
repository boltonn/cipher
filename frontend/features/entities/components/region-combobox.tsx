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
import { useSelectorRegions } from "@/features/entities/hooks/use-entities";
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown, Globe, X } from "lucide-react";
import { useMemo, useState } from "react";

interface RegionComboboxProps {
  /** ISO-3166-1 alpha-2 country code. */
  value?: string;
  onChange: (code: string | undefined) => void;
  className?: string;
}

let regionNames: Intl.DisplayNames | undefined;
function countryName(code: string): string {
  try {
    regionNames ??= new Intl.DisplayNames(["en"], { type: "region" });
    return regionNames.of(code) ?? code;
  } catch {
    return code;
  }
}

/**
 * Single-select country picker whose value is exactly one of the ISO-3166-1
 * alpha-2 codes the backend phone normalizer accepts (`GET /entities/selector-regions`).
 */
export function RegionCombobox({ value, onChange, className }: RegionComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const { data: regions = [], isPending } = useSelectorRegions();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const withNames = regions.map((r) => ({ ...r, name: countryName(r.code) }));
    if (!q) return withNames;
    return withNames.filter(
      (r) =>
        r.code.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        String(r.callingCode).includes(q)
    );
  }, [regions, query]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "h-10 w-full justify-between border-border bg-muted/40 text-sm hover:bg-muted/60",
            className
          )}
        >
          <span
            className={cn(
              "flex items-center gap-2 truncate",
              value ? "text-foreground" : "text-muted-foreground"
            )}
          >
            <Globe size={13} className="shrink-0 text-muted-foreground" />
            {value ? `${countryName(value)} (${value})` : "No country"}
          </span>
          {value ? (
            <span
              role="button"
              tabIndex={0}
              aria-label="Clear country"
              className="ml-2 shrink-0 text-muted-foreground hover:text-white"
              onClick={(e) => {
                e.stopPropagation();
                onChange(undefined);
              }}
            >
              <X size={12} />
            </span>
          ) : (
            <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-muted-foreground" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 border-border bg-popover p-0">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search country or code…"
            value={query}
            onValueChange={setQuery}
            className="text-xs"
          />
          <CommandList>
            {!isPending && filtered.length === 0 && (
              <CommandEmpty className="py-4 text-xs text-muted-foreground">
                No match
              </CommandEmpty>
            )}
            <CommandGroup>
              {filtered.map((r) => (
                <CommandItem
                  key={r.code}
                  value={r.code}
                  onSelect={() => {
                    onChange(r.code === value ? undefined : r.code);
                    setOpen(false);
                  }}
                  className="gap-2 text-xs"
                >
                  <Check
                    className={cn(
                      "h-3 w-3 shrink-0",
                      r.code === value ? "opacity-100" : "opacity-0"
                    )}
                  />
                  <span className="flex-1 truncate">{r.name}</span>
                  <span className="font-mono text-muted-foreground">
                    {r.code} · +{r.callingCode}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
