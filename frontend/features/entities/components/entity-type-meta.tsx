import type { EntityType } from "@/features/entities/types";
import { Building2, Fingerprint, MapPin, User, type LucideIcon } from "lucide-react";

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
