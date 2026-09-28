import {
  SELECTOR_TYPE_LABELS,
  type EntityType,
  type SelectorType,
} from "@/features/entities/types";
import {
  AtSign,
  Bitcoin,
  Building2,
  Car,
  CreditCard,
  Fingerprint,
  IdCard,
  Landmark,
  Mail,
  MapPin,
  Network,
  Phone,
  Smartphone,
  User,
  type LucideIcon,
} from "lucide-react";

/**
 * The four entity types need four visually distinct colors (graph nodes, badges,
 * mention marks). There is no 4-way semantic token set for this in globals.css,
 * so a small documented palette lives here -- analogous to the documented
 * cyan/indigo exception in the search feature. Amber is intentionally NOT used:
 * it is reserved for AI/ML annotation surfaces.
 */
export interface EntityTypeMeta {
  label: string;
  Icon: LucideIcon;
  /** hex used by the SVG graph nodes */
  color: string;
  /** tailwind classes for badges / mention marks */
  textClass: string;
  bgClass: string;
  borderClass: string;
  markClass: string;
}

export const ENTITY_TYPE_META: Record<EntityType, EntityTypeMeta> = {
  person: {
    label: "Person",
    Icon: User,
    color: "#38bdf8",
    textClass: "text-sky-300",
    bgClass: "bg-sky-500/10",
    borderClass: "border-sky-500/30",
    markClass: "bg-sky-400/25 decoration-sky-400/60",
  },
  organization: {
    label: "Organization",
    Icon: Building2,
    color: "#a78bfa",
    textClass: "text-violet-300",
    bgClass: "bg-violet-500/10",
    borderClass: "border-violet-500/30",
    markClass: "bg-violet-400/25 decoration-violet-400/60",
  },
  location: {
    label: "Location",
    Icon: MapPin,
    color: "#2dd4bf",
    textClass: "text-teal-300",
    bgClass: "bg-teal-500/10",
    borderClass: "border-teal-500/30",
    markClass: "bg-teal-400/25 decoration-teal-400/60",
  },
  selector: {
    label: "Selector",
    Icon: Fingerprint,
    color: "#f472b6",
    textClass: "text-pink-300",
    bgClass: "bg-pink-500/10",
    borderClass: "border-pink-500/30",
    markClass: "bg-pink-400/25 decoration-pink-400/60",
  },
};

/**
 * Per-kind icon for a selector. A selector node/badge is far more legible when
 * a phone reads as a phone and an email as an envelope, rather than every
 * selector being the same fingerprint glyph. Colour still comes from
 * `ENTITY_TYPE_META.selector` -- this only varies the icon and label.
 */
export const SELECTOR_TYPE_META: Record<
  SelectorType,
  { label: string; Icon: LucideIcon }
> = {
  phone: { label: SELECTOR_TYPE_LABELS.phone, Icon: Phone },
  email: { label: SELECTOR_TYPE_LABELS.email, Icon: Mail },
  ip: { label: SELECTOR_TYPE_LABELS.ip, Icon: Network },
  iban: { label: SELECTOR_TYPE_LABELS.iban, Icon: Landmark },
  bank_card: { label: SELECTOR_TYPE_LABELS.bank_card, Icon: CreditCard },
  passport: { label: SELECTOR_TYPE_LABELS.passport, Icon: IdCard },
  national_id: { label: SELECTOR_TYPE_LABELS.national_id, Icon: IdCard },
  imei: { label: SELECTOR_TYPE_LABELS.imei, Icon: Smartphone },
  imsi: { label: SELECTOR_TYPE_LABELS.imsi, Icon: Smartphone },
  social_handle: { label: SELECTOR_TYPE_LABELS.social_handle, Icon: AtSign },
  crypto_address: { label: SELECTOR_TYPE_LABELS.crypto_address, Icon: Bitcoin },
  license_plate: { label: SELECTOR_TYPE_LABELS.license_plate, Icon: Car },
};

/** Icon for an entity, refined by selector kind where one is known. */
export function entityGlyph(
  entityType: EntityType,
  selectorType?: SelectorType | null
): LucideIcon {
  if (entityType === "selector" && selectorType) {
    return SELECTOR_TYPE_META[selectorType]?.Icon ?? Fingerprint;
  }
  return ENTITY_TYPE_META[entityType].Icon;
}
