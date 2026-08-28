import { Badge } from "@/components/ui/badge";
import { ENTITY_TYPE_META } from "@/features/entities/components/entity-type-meta";
import type { EntityType } from "@/features/entities/types";
import { cn } from "@/lib/utils";

interface EntityTypeBadgeProps {
  type: EntityType;
  /** selector kind, shown in parens for selector entities */
  detail?: string | null;
  /** unresolved / model-predicted -- rendered with the amber annotation ring */
  suggested?: boolean;
  className?: string;
}

export function EntityTypeBadge({ type, detail, suggested, className }: EntityTypeBadgeProps) {
  const meta = ENTITY_TYPE_META[type];
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 gap-1.5 px-2 text-[10px] font-bold uppercase tracking-widest",
        meta.bgClass,
        meta.textClass,
        meta.borderClass,
        suggested && "ring-1 ring-annotation/50 border-annotation/40",
        className
      )}
    >
      <meta.Icon size={11} />
      {meta.label}
      {detail ? <span className="normal-case tracking-normal opacity-70">· {detail}</span> : null}
    </Badge>
  );
}
