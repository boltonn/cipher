"use client";

import { Badge } from "@/components/ui/badge";
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
import { useCreatePerson, usePersonSearch } from "@/features/persons/hooks/use-persons";
import { cn } from "@/lib/utils";
import { Check, ChevronsUpDown, Plus, UserRound } from "lucide-react";
import { useState } from "react";

interface PersonPickerProps {
  value?: string;
  valueName?: string;
  onSelect: (personId: string, personName?: string) => void;
  className?: string;
  /** Trigger text shown when nothing is picked. */
  placeholder?: string;
}

export function PersonPicker({
  value,
  valueName,
  onSelect,
  className,
  placeholder = "Select a person…",
}: PersonPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const { data, isFetching } = usePersonSearch({ query: query || undefined, limit: 20, page: 1 });
  const createPerson = useCreatePerson((personId) => {
    onSelect(personId, query);
    setOpen(false);
    setQuery("");
  });

  const persons = data?.data ?? [];
  const exactMatch = persons.some((p) => p.name?.toLowerCase() === query.trim().toLowerCase());

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "w-full justify-between bg-muted/40 border-border hover:bg-muted/60 text-xs h-10",
            className
          )}
        >
          <span className="flex items-center gap-2 truncate">
            <UserRound size={14} className="text-muted-foreground shrink-0" />
            {valueName ?? value ?? placeholder}
          </span>
          <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0 bg-popover border-border">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search people..."
            value={query}
            onValueChange={setQuery}
            className="text-xs"
          />
          <CommandList>
            {!isFetching && persons.length === 0 && !query && (
              <CommandEmpty className="text-xs text-muted-foreground py-4">
                Type to search or create a person
              </CommandEmpty>
            )}
            <CommandGroup>
              {persons.map((person) => (
                <CommandItem
                  key={person.id}
                  value={person.id}
                  onSelect={() => {
                    onSelect(person.id, person.name);
                    setOpen(false);
                    setQuery("");
                  }}
                  className="text-xs gap-2"
                >
                  <Check
                    className={cn("h-3 w-3", value === person.id ? "opacity-100" : "opacity-0")}
                  />
                  <span className="truncate flex-1">{person.name || "Unnamed"}</span>
                  {person.isVerified && (
                    <Badge className="bg-primary/10 text-primary border-none text-[8px] px-1 py-0">
                      Verified
                    </Badge>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
            {query.trim() && !exactMatch && (
              <CommandGroup>
                <CommandItem
                  value={`create-${query}`}
                  onSelect={() => createPerson.mutate({ name: query.trim() })}
                  disabled={createPerson.isPending}
                  className="text-xs gap-2 text-annotation"
                >
                  <Plus className="h-3 w-3" />
                  Create &quot;{query.trim()}&quot;
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
