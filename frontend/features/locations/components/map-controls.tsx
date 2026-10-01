"use client";

import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { COLOR_FIELDS } from "@/features/locations/lib/marker-style";
import { MAP_STYLES, useMapStyleStore } from "@/features/locations/style-store";
import { Check, Layers, Palette, type LucideIcon } from "lucide-react";

interface Option<T extends string> {
  id: T;
  label: string;
}

/** One icon button in the display group, opening a single-choice menu beside it. */
function OptionMenu<T extends string>({
  label,
  icon: Icon,
  options,
  value,
  onChange,
}: {
  label: string;
  icon: LucideIcon;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button variant="secondary" size="icon" className="size-9" aria-label={label}>
              <Icon className="size-4" />
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={6}>
          {label}
        </TooltipContent>
      </Tooltip>
      <PopoverContent side="right" align="end" sideOffset={8} className="w-44 p-1">
        <p className="px-2 pb-1 pt-1.5 text-xs font-medium text-muted-foreground">{label}</p>
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
          >
            {option.label}
            {option.id === value && <Check className="size-3.5 text-primary" />}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

/** Floating display preferences: basemap (tile server) and point colouring. */
export function MapControls() {
  const { styleId, setStyleId, colorField, setColorField } = useMapStyleStore();

  return (
    <TooltipProvider delayDuration={300}>
      <ButtonGroup orientation="vertical" aria-label="Map display" className="rounded-lg shadow-md">
        <OptionMenu
          label="Basemap"
          icon={Layers}
          options={MAP_STYLES}
          value={styleId}
          onChange={setStyleId}
        />
        <OptionMenu
          label="Colour points by"
          icon={Palette}
          options={COLOR_FIELDS}
          value={colorField}
          onChange={setColorField}
        />
      </ButtonGroup>
    </TooltipProvider>
  );
}
