"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import { Loader2, RotateCw, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

interface PageLoadingProps {
  /** Optional glyph shown inside the spinner ring. */
  icon?: IconComponent;
  /** Short status line, rendered as a quiet caption. */
  label?: string;
  /**
   * Accent family. `annotation` (amber) is reserved for AI/ML surfaces such
   * as Faces -- everywhere else stays on `primary`.
   */
  accent?: "primary" | "annotation";
  /**
   * Seconds to wait before offering a manual retry under the spinner. A
   * request that never resolves stops looking like progress and starts
   * looking stuck; this gives the user a way out. Only shown when `onRetry`
   * is passed.
   */
  slowAfter?: number;
  onRetry?: () => void;
  className?: string;
}

const ACCENT = {
  primary: {
    ring: "text-primary/20",
    glyph: "text-primary",
  },
  annotation: {
    ring: "text-annotation/20",
    glyph: "text-annotation",
  },
} as const;

/**
 * Full-height centered loader for page- and panel-level pending states:
 * a spinner ring with an optional glyph and a quiet status line.
 * Small inline spinners inside rows/buttons stay as bare `Loader2`.
 */
export function PageLoading({
  icon: Icon,
  label,
  accent = "primary",
  slowAfter = 12,
  onRetry,
  className,
}: PageLoadingProps) {
  const tone = ACCENT[accent];
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!onRetry) return;
    const id = setTimeout(() => setSlow(true), slowAfter * 1000);
    return () => clearTimeout(id);
  }, [onRetry, slowAfter]);

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-24 text-muted-foreground",
        className
      )}
    >
      <div className="relative mb-4 flex items-center justify-center">
        <Loader2 className={cn("h-8 w-8 animate-spin", tone.ring)} />
        {Icon && (
          <Icon className={cn("absolute h-3.5 w-3.5 animate-pulse", tone.glyph)} />
        )}
      </div>
      {label && (
        <p
className="text-xs text-muted-foreground"
        >
          {label}
        </p>
      )}
      {slow && onRetry && (
        <div className="mt-6 flex flex-col items-center gap-2">
          <p className="text-xs text-muted-foreground">Taking longer than usual.</p>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={() => {
              setSlow(false);
              onRetry();
            }}
          >
            <RotateCw size={13} />
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}

interface PageErrorProps {
  /** Short, human title. Defaults to a generic load-failure line. */
  title?: string;
  /** One supporting sentence. Never a stack trace or a raw error string. */
  body?: string;
  onRetry?: () => void;
  className?: string;
}

/**
 * The shared "the request failed" panel. Use this instead of surfacing an
 * error object, a status code, or a query string -- the user gets a plain
 * sentence and a Retry button, nothing from the wire.
 */
export function PageError({
  title = "Couldn’t load this",
  body = "The request failed. This is usually temporary — try again.",
  onRetry,
  className,
}: PageErrorProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-destructive/30 bg-destructive/[0.03] px-6 py-24 text-center",
        className
      )}
    >
      <TriangleAlert className="size-6 text-destructive/70" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">{body}</p>
      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          className="mt-1 h-8 gap-1.5 text-xs"
          onClick={onRetry}
        >
          <RotateCw size={13} />
          Retry
        </Button>
      )}
    </div>
  );
}
