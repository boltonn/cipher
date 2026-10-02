"use client";

import { EyeOff, Focus, Maximize2, Sparkles, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface GraphSelectionBarProps {
  count: number;
  onExpand: () => void;
  onIsolate: () => void;
  onHide: () => void;
  onAddSeeds: () => void;
  onClear: () => void;
}

/** Bulk actions for the ctrl-click selection; floats over the top of the canvas. */
export function GraphSelectionBar({
  count,
  onExpand,
  onIsolate,
  onHide,
  onAddSeeds,
  onClear,
}: GraphSelectionBarProps) {
  return (
    <div className="absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-1 rounded-lg border border-border bg-card/95 p-1 text-xs shadow-xl backdrop-blur-sm">
      <span className="px-2 font-semibold text-foreground">{count} selected</span>
      <Action icon={Maximize2} onClick={onExpand}>
        Expand
      </Action>
      <Action icon={Focus} onClick={onIsolate}>
        Isolate
      </Action>
      <Action icon={EyeOff} onClick={onHide}>
        Hide
      </Action>
      <Action icon={Sparkles} onClick={onAddSeeds}>
        Pin as seeds
      </Action>
      <button
        type="button"
        onClick={onClear}
        aria-label="Clear selection"
        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        <X size={13} />
      </button>
    </div>
  );
}

function Action({
  icon: Icon,
  onClick,
  children,
}: {
  icon: LucideIcon;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <Icon size={13} className="shrink-0" />
      {children}
    </button>
  );
}
