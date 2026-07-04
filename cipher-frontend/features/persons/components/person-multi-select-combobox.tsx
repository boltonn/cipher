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
import { facesService } from "@/features/faces/api";
import { getFaceCropStyle } from "@/features/faces/components/face-crop";
import { usePerson, usePersonRepresentativeFaces, usePersonSearch } from "@/features/persons/hooks/use-persons";
import { Person } from "@/features/persons/types";
import { cn } from "@/lib/utils";
import { BadgeCheck, Check, ChevronsUpDown, UserRound, X } from "lucide-react";
import { useState } from "react";

interface PersonMultiSelectComboboxProps {
  value: string[];
  onChange: (personIds: string[]) => void;
  placeholder?: string;
  className?: string;
}

/**
 * Multi-select identity filter: type-ahead search by name or tag, each
 * option showing a tiny circular thumbnail of the person's primary face.
 */
export function PersonMultiSelectCombobox({
  value,
  onChange,
  placeholder = "Filter by identity...",
  className,
}: PersonMultiSelectComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const { data, isFetching } = usePersonSearch({ query: query || undefined, limit: 20, page: 1 });
  const persons = data?.data ?? [];

  const toggle = (personId: string) => {
    const next = new Set(value);
    if (next.has(personId)) next.delete(personId);
    else next.add(personId);
    onChange(Array.from(next));
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between bg-slate-900/40 border-white/10 hover:bg-slate-900/60 text-xs h-9"
          >
            <span className="flex items-center gap-2 truncate text-slate-400">
              <UserRound size={14} className="text-slate-500 shrink-0" />
              {value.length > 0 ? `${value.length} selected` : placeholder}
            </span>
            <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 text-slate-600" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0 bg-popover border-white/10">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Search name or tag..."
              value={query}
              onValueChange={setQuery}
              className="text-xs"
            />
            <CommandList>
              {!isFetching && persons.length === 0 && (
                <CommandEmpty className="text-xs text-slate-500 py-4">No people found</CommandEmpty>
              )}
              <CommandGroup>
                {persons.map((person) => (
                  <PersonOptionRow
                    key={person.id}
                    person={person}
                    selected={value.includes(person.id)}
                    onSelect={() => toggle(person.id)}
                  />
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((personId) => (
            <SelectedPersonChip key={personId} personId={personId} onRemove={() => toggle(personId)} />
          ))}
        </div>
      )}
    </div>
  );
}

function SelectedPersonChip({ personId, onRemove }: { personId: string; onRemove: () => void }) {
  const { data: person } = usePerson(personId);

  return (
    <Badge className="h-6 bg-indigo-500/10 text-indigo-300 border-none text-[11px] font-medium gap-1 pr-1.5">
      {person?.name || "Unnamed"}
      <button
        type="button"
        onClick={onRemove}
        className="hover:text-white ml-0.5"
        aria-label={`Remove ${person?.name || "person"}`}
      >
        <X size={11} />
      </button>
    </Badge>
  );
}

function PersonOptionRow({
  person,
  selected,
  onSelect,
}: {
  person: Person;
  selected: boolean;
  onSelect: () => void;
}) {
  const { data: faces } = usePersonRepresentativeFaces(person.id);
  const primaryFace = faces?.[0];
  const cropStyle = primaryFace
    ? getFaceCropStyle(primaryFace.boundingBox, facesService.getFaceViewUrl(primaryFace.id))
    : undefined;

  return (
    <CommandItem value={person.id} onSelect={onSelect} className="text-xs gap-2">
      <Check className={cn("h-3 w-3 shrink-0", selected ? "opacity-100" : "opacity-0")} />
      <div
        className="h-5 w-5 rounded-full shrink-0 overflow-hidden bg-indigo-500/10 bg-cover bg-center text-indigo-300 text-[8px] font-black flex items-center justify-center"
        style={cropStyle}
      >
        {!primaryFace && (person.name ? person.name[0].toUpperCase() : <UserRound size={10} />)}
      </div>
      <span className="truncate flex-1">{person.name || "Unnamed"}</span>
      {person.isVerified && <BadgeCheck size={12} className="text-indigo-400 shrink-0" />}
    </CommandItem>
  );
}
