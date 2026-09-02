import { cn } from "@/lib/utils";
import type { IconComponent } from "@/types/common";
import { Loader2 } from "lucide-react";

interface PageLoadingProps {
  /** Optional glyph shown inside the spinner ring. */
  icon?: IconComponent;
  /** Short status line, rendered in the spaced-uppercase treatment. */
  label?: string;
  /**
   * Accent family. `annotation` (amber) is reserved for AI/ML surfaces such
   * as Faces -- everywhere else stays on `primary`.
   */
  accent?: "primary" | "annotation";
  className?: string;
}

const ACCENT = {
  primary: {
    ring: "text-primary/20",
    glyph: "text-primary",
    label: "text-primary/50",
  },
  annotation: {
    ring: "text-annotation/20",
    glyph: "text-annotation",
    label: "text-annotation/50",
  },
} as const;

/**
 * Full-height centered loader for page- and panel-level pending states:
 * a spinner ring with an optional glyph and a spaced-uppercase status line.
 * Small inline spinners inside rows/buttons stay as bare `Loader2`.
 */
export function PageLoading({
  icon: Icon,
  label,
  accent = "primary",
  className,
}: PageLoadingProps) {
  const tone = ACCENT[accent];

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-48 text-muted-foreground",
        className
      )}
    >
      <div className="relative mb-6 flex items-center justify-center">
        <Loader2 className={cn("h-12 w-12 animate-spin", tone.ring)} />
        {Icon && (
          <Icon className={cn("absolute h-5 w-5 animate-pulse", tone.glyph)} />
        )}
      </div>
      {label && (
        <p
          className={cn(
            // pl offsets the trailing letter-spacing so the text optically
            // centers under the spinner.
            "pl-[0.5em] text-[10px] font-bold uppercase italic tracking-[0.5em]",
            tone.label
          )}
        >
          {label}
        </p>
      )}
    </div>
  );
}
