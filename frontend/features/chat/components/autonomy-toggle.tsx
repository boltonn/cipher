"use client";

import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useChatStore } from "../hooks/use-chat-store";
import type { ChatAutonomy } from "../types";

const OPTIONS: { value: ChatAutonomy; label: string; hint: string }[] = [
  {
    value: "guided",
    label: "Guided",
    hint: "Checks in before reading through a large result set or proposing many changes.",
  },
  { value: "auto", label: "Auto", hint: "Answers without checking in; says what it assumed." },
];

/** How often the assistant stops to let the analyst steer. */
export function AutonomyToggle() {
  const autonomy = useChatStore((state) => state.autonomy);
  const setAutonomy = useChatStore((state) => state.setAutonomy);
  return (
    <ButtonGroup>
      {OPTIONS.map((option) => (
        <Tooltip key={option.value}>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-pressed={autonomy === option.value}
              onClick={() => setAutonomy(option.value)}
              className={cn(
                "h-7 border-border px-2 text-xs",
                autonomy === option.value
                  ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                  : "bg-muted/40 text-muted-foreground hover:text-foreground"
              )}
            >
              {option.label}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{option.hint}</TooltipContent>
        </Tooltip>
      ))}
    </ButtonGroup>
  );
}
