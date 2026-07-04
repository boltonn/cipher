"use client";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { PaginationModeType } from "@/types/common";
import { Infinity as InfinityIcon, Zap } from "lucide-react";

interface PaginationModeToggleProps {
  mode: PaginationModeType;
  onToggle: () => void;
  /** Text/hover accent color class, e.g. "hover:text-indigo-400" or "hover:text-annotation". */
  accentClassName?: string;
  className?: string;
}

/** Icon-only infinite-scroll/paginated toggle, shared across list/gallery pages. */
export function PaginationModeToggle({
  mode,
  onToggle,
  accentClassName = "hover:text-indigo-400",
  className,
}: PaginationModeToggleProps) {
  return (
    <TooltipProvider>
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="icon"
            onClick={onToggle}
            aria-label={
              mode === "infinite" ? "Switch to paginated mode" : "Switch to infinite scroll mode"
            }
            className={cn(
              "h-9 w-9 border-white/5 bg-slate-900/40 text-slate-400",
              accentClassName,
              className
            )}
          >
            {mode === "infinite" ? <InfinityIcon size={16} /> : <Zap size={16} />}
          </Button>
        </TooltipTrigger>
        <TooltipContent
          side="bottom"
          className="text-[9px] font-bold uppercase tracking-widest"
        >
          {mode === "infinite" ? "Infinite scroll" : "Paginated"}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
