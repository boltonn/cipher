import { cn } from "@/lib/utils";
import type { IconComponent } from "@/types/common";

interface EmptyStateProps {
  /** Glyph shown above the title. */
  icon: IconComponent;
  title: string;
  /** Optional supporting sentence under the title. */
  body?: string;
  /** Optional call to action (e.g. a "Reset filters" button). */
  action?: React.ReactNode;
  className?: string;
}

/**
 * The shared "nothing here" panel for list and tab views -- dashed card,
 * centered glyph, one line of copy. Use this instead of hand-rolling a
 * bordered div so every empty view reads the same.
 */
export function EmptyState({ icon: Icon, title, body, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-border/50 bg-muted/10 px-6 py-24 text-center",
        className
      )}
    >
      <Icon className="size-6 text-muted-foreground/50" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      {body && (
        <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">{body}</p>
      )}
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}
