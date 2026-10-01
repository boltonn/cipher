import { Badge } from "@/components/ui/badge";
import {
  ENTITY_TYPE_META,
  SELECTOR_TYPE_META,
} from "@/features/entities/components/entity-type-meta";
import {
  SELECTOR_SUBTYPE_TYPE,
  SELECTOR_SUBTYPES,
  SELECTOR_TYPES,
  type EntityType,
  type SelectorSubtype,
  type SelectorType,
} from "@/features/entities/types";
import { cn } from "@/lib/utils";

interface EntityTypeBadgeProps {
  type: EntityType;
  /** selector type, shown as the label/icon for selector entities */
  detail?: string | null;
  /** selector subtype (telegram, btc_address, ...), shown after the label */
  subtype?: string | null;
  /** unresolved / model-predicted -- rendered with the amber annotation ring */
  suggested?: boolean;
  className?: string;
}

function asSelectorType(value?: string | null): SelectorType | null {
  return value && (SELECTOR_TYPES as readonly string[]).includes(value)
    ? (value as SelectorType)
    : null;
}

function asSelectorSubtype(value?: string | null): SelectorSubtype | null {
  return value && (SELECTOR_SUBTYPES as readonly string[]).includes(value)
    ? (value as SelectorSubtype)
    : null;
}

export function EntityTypeBadge({
  type,
  detail,
  subtype,
  suggested,
  className,
}: EntityTypeBadgeProps) {
  const meta = ENTITY_TYPE_META[type];

  const sub = type === "selector" ? asSelectorSubtype(subtype) : null;
  // Icon + label come from the selector type; fall back to a subtype's parent.
  const kind =
    type === "selector"
      ? (asSelectorType(detail) ?? (sub ? SELECTOR_SUBTYPE_TYPE[sub] : null))
      : null;
  const kindMeta = kind ? SELECTOR_TYPE_META[kind] : null;
  const Icon = kindMeta?.Icon ?? meta.Icon;
  const label = kindMeta?.label ?? meta.label;
  const trailing = sub ? sub.replace(/_/g, " ") : kind ? null : detail;

  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 gap-1.5 px-2 text-[11px] font-bold uppercase tracking-wide",
        meta.bgClass,
        meta.textClass,
        meta.borderClass,
        suggested && "ring-1 ring-annotation/50 border-annotation/40",
        className
      )}
    >
      <Icon size={11} />
      {label}
      {trailing ? (
        <span className="normal-case tracking-normal opacity-70">· {trailing}</span>
      ) : null}
    </Badge>
  );
}
