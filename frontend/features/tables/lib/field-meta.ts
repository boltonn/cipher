import { ENTITY_TYPE_META, entityGlyph } from "@/features/entities/components/entity-type-meta";
import { SELECTOR_TYPES, type EntityType, type SelectorType } from "@/features/entities/types";
import type { ColumnDecision, FieldTypeOption } from "@/features/tables/types";
import { OTHER_FIELD } from "@/features/tables/types";
import { AlignLeft, ArrowLeftRight, CalendarClock, Hash, Minus, type LucideIcon } from "lucide-react";

const GROUP_ICON: Record<string, LucideIcon> = {
  time: CalendarClock,
  edge: ArrowLeftRight,
  key: Hash,
};

function asSelectorType(value: string | null): SelectorType | undefined {
  return SELECTOR_TYPES.includes(value as SelectorType) ? (value as SelectorType) : undefined;
}

/** The glyph for a field type: the entity / selector icon used everywhere else, or a neutral one. */
export function fieldIcon(field: FieldTypeOption | undefined): LucideIcon {
  if (!field || field.id === OTHER_FIELD) return Minus;
  if (field.id === "other.free_text") return AlignLeft;
  if (field.entityType) return entityGlyph(field.entityType as EntityType, asSelectorType(field.selectorType));
  return GROUP_ICON[field.group] ?? Minus;
}

/**
 * A column's type chip, in the same three states as a mention chip in the text view:
 * a model proposal is dashed amber until someone verifies the mapping, a type you set (or verified)
 * takes its entity's colour, `other` is a ghost.
 */
export function chipClass(column: ColumnDecision, field: FieldTypeOption | undefined, isVerified: boolean): string {
  if (column.fieldType === OTHER_FIELD) return "border-dashed border-border text-muted-foreground";
  if (column.decisionSource === "model" && !isVerified) return "border-dashed border-annotation/50 bg-annotation/10 text-annotation";
  const meta = field?.entityType ? ENTITY_TYPE_META[field.entityType as EntityType] : null;
  return meta ? `${meta.bgClass} ${meta.textClass} ${meta.borderClass}` : "border-border bg-muted/60 text-foreground";
}

export const FIELD_GROUP_LABELS: Record<string, string> = {
  person: "Person",
  organization: "Organization",
  location: "Location",
  selector: "Selector",
  time: "Time",
  edge: "On the relationship",
  key: "Key",
  other: "Other",
};
