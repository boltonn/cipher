import type { EventStatus, EventType } from "@/features/events/types";
import {
  CalendarClock,
  CalendarDays,
  Hourglass,
  type LucideIcon,
  MapPin,
  Package,
  Plane,
  UtensilsCrossed,
  Users,
} from "lucide-react";

/**
 * Events colour by **category** (derived from `eventType` server-side), not by
 * type -- so travel + lodging read as one trip colour on the calendar. There is
 * no semantic token set for these six buckets in globals.css, so a small
 * documented palette lives here, matching the `entity-type-meta` precedent.
 * Amber is intentionally avoided: reserved for AI/ML annotation surfaces.
 */
export interface EventCategoryMeta {
  label: string;
  /** hex for calendar chips / dots */
  color: string;
  textClass: string;
  bgClass: string;
  borderClass: string;
  dotClass: string;
}

export const EVENT_CATEGORY_META: Record<string, EventCategoryMeta> = {
  travel: {
    label: "Travel",
    color: "#38bdf8",
    textClass: "text-sky-300",
    bgClass: "bg-sky-500/10",
    borderClass: "border-sky-500/30",
    dotClass: "bg-sky-400",
  },
  personal: {
    label: "Personal",
    color: "#2dd4bf",
    textClass: "text-teal-300",
    bgClass: "bg-teal-500/10",
    borderClass: "border-teal-500/30",
    dotClass: "bg-teal-400",
  },
  work: {
    label: "Work",
    color: "#a78bfa",
    textClass: "text-violet-300",
    bgClass: "bg-violet-500/10",
    borderClass: "border-violet-500/30",
    dotClass: "bg-violet-400",
  },
  admin: {
    label: "Admin",
    color: "#f472b6",
    textClass: "text-pink-300",
    bgClass: "bg-pink-500/10",
    borderClass: "border-pink-500/30",
    dotClass: "bg-pink-400",
  },
  logistics: {
    label: "Logistics",
    color: "#fb923c",
    textClass: "text-orange-300",
    bgClass: "bg-orange-500/10",
    borderClass: "border-orange-500/30",
    dotClass: "bg-orange-400",
  },
  other: {
    label: "Other",
    color: "#94a3b8",
    textClass: "text-slate-300",
    bgClass: "bg-slate-500/10",
    borderClass: "border-slate-500/30",
    dotClass: "bg-slate-400",
  },
};

export interface EventTypeMeta {
  label: string;
  Icon: LucideIcon;
  category: string;
}

export const EVENT_TYPE_META: Record<EventType, EventTypeMeta> = {
  travel: { label: "Travel", Icon: Plane, category: "travel" },
  lodging: { label: "Lodging", Icon: MapPin, category: "travel" },
  reservation: {
    label: "Reservation",
    Icon: UtensilsCrossed,
    category: "personal",
  },
  meeting: { label: "Meeting", Icon: Users, category: "work" },
  deadline: { label: "Deadline", Icon: Hourglass, category: "admin" },
  delivery: { label: "Delivery", Icon: Package, category: "logistics" },
  occasion: { label: "Occasion", Icon: CalendarDays, category: "personal" },
  other: { label: "Other", Icon: CalendarClock, category: "other" },
};

export function categoryMeta(category: string): EventCategoryMeta {
  return EVENT_CATEGORY_META[category] ?? EVENT_CATEGORY_META.other;
}

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  confirmed: "Confirmed",
  tentative: "Tentative",
  cancelled: "Cancelled",
  completed: "Completed",
};
