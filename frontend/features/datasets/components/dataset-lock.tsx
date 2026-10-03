"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { Lock } from "lucide-react";

export const LOCKED_DATASET_HINT =
  "Discoverable, but you don't have access. Ask an admin to add you.";

/** Marks a discoverable dataset the user isn't a member of: it can't be opened, triaged or searched. */
export function DatasetLock({
  size = 12,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Lock
          size={size}
          aria-label="No access"
          className={cn("shrink-0 text-muted-foreground", className)}
        />
      </TooltipTrigger>
      <TooltipContent>{LOCKED_DATASET_HINT}</TooltipContent>
    </Tooltip>
  );
}
