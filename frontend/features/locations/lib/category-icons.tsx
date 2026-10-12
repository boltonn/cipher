"use client";

import { cn, humanize } from "@/lib/utils";
import { createElement, type CSSProperties } from "react";
import {
  Banknote,
  BatteryCharging,
  Briefcase,
  Building2,
  Bus,
  Camera,
  Coffee,
  Cross,
  Dumbbell,
  FileText,
  Fingerprint,
  Flag,
  Flame,
  Fuel,
  Globe,
  GraduationCap,
  History,
  Home,
  Hotel,
  Landmark,
  Lock,
  Mailbox,
  Map as MapIcon,
  MapPin,
  MapPinned,
  Navigation,
  ParkingCircle,
  Pill,
  Plane,
  Scale,
  Shield,
  ShieldAlert,
  ShoppingCart,
  Sofa,
  Store,
  Tent,
  TrafficCone,
  TrainFront,
  Trees,
  Utensils,
  Waves,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";

/** Which feature property drives the marker icon + colour. Mirrors `ColorField`. */
type Field = "source" | "category";

export const FALLBACK_COLOR = "#8a9099";

/**
 * Single source of truth for a location's icon + colour. Every map marker,
 * legend row, and detail header resolves through here so `exif` (or `camera`)
 * looks identical everywhere. Colours are fixed hex -- not design tokens -- so a
 * marker never resolves to a near-white token on a light basemap.
 */
const SOURCE_ICONS: Record<string, LucideIcon> = {
  exif: Camera,
  coordinateMention: FileText,
  nameMention: MapPinned,
  geocoded: MapPin,
  deviceGps: Navigation,
};

const SOURCE_COLORS: Record<string, string> = {
  exif: "#4c6ef5", // blue
  coordinateMention: "#e8590c", // orange
  nameMention: "#7048e8", // violet
  geocoded: "#0c8599", // teal
  deviceGps: "#2f9e44", // green
};

// Gazetteer levels (`city` ... `country`) come from `resolve-locations`; the POI
// kinds are ported from shadowbot so the two apps stay visually aligned.
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  city: Building2,
  admin1: MapIcon,
  region: MapPinned,
  country: Globe,
  gas_station: Fuel,
  ev_charging: BatteryCharging,
  supermarket: ShoppingCart,
  restaurant: Utensils,
  cafe: Coffee,
  parking: ParkingCircle,
  rest_area: Sofa,
  hotel: Hotel,
  pharmacy: Pill,
  hospital: Cross,
  gym: Dumbbell,
  park: Trees,
  bank: Landmark,
  atm: Banknote,
  car_repair: Wrench,
  campground: Tent,
  camera: Camera,
  police: ShieldAlert,
  fire_station: Flame,
  military: Shield,
  embassy: Flag,
  government: Building2,
  courthouse: Scale,
  prison: Lock,
  border_control: Fingerprint,
  post_office: Mailbox,
  power_substation: Zap,
  airport: Plane,
  toll_booth: TrafficCone,
  traffic_signals: TrafficCone,
  school: GraduationCap,
  bus_stop: Bus,
  railway_station: TrainFront,
  water: Waves,
  mall: Store,
  home: Home,
  work: Briefcase,
  unknown: History,
};

const CATEGORY_COLORS: Record<string, string> = {
  city: "#4c6ef5",
  admin1: "#0c8599",
  region: "#e8590c",
  country: "#7048e8",
  camera: "#e5484d",
  police: "#4263eb",
  military: "#5c940d",
  fire_station: "#f03e3e",
  prison: "#c2255c",
  courthouse: "#9c36b5",
  border_control: "#e8590c",
  power_substation: "#f59f00",
  toll_booth: "#f08c00",
  embassy: "#ae3ec9",
  government: "#7048e8",
  post_office: "#d9480f",
  school: "#1c7ed6",
  bus_stop: "#1098ad",
  railway_station: "#0c8599",
  airport: "#1971c2",
  traffic_signals: "#f76707",
  gas_station: "#e8940c",
  ev_charging: "#2f9e44",
  supermarket: "#37b24d",
  restaurant: "#f76707",
  cafe: "#a9762f",
  parking: "#4c6ef5",
  rest_area: "#868e96",
  hotel: "#7950f2",
  pharmacy: "#d6336c",
  hospital: "#e03131",
  gym: "#f783ac",
  campground: "#66a80f",
  car_repair: "#495057",
  bank: "#364fc7",
  atm: "#1c7ed6",
  mall: "#d6336c",
  park: "#2f9e44",
  water: "#1c7ed6",
  home: "#12b886",
  work: "#7048e8",
  unknown: "#868e96",
};

const SOURCE_LABELS: Record<string, string> = {
  nameMention: "Place name in text",
  coordinateMention: "Coordinates in text",
  exif: "Photo EXIF",
  geocoded: "Geocoded address",
  deviceGps: "Device GPS",
};

function key(value: string | null | undefined): string | null {
  return value ? value.toLowerCase() : null;
}

/** Icon for a `source` / `category` value. Falls back to a generic pin. */
export function iconFor(field: Field, value: string | null | undefined): LucideIcon {
  const k = key(value);
  if (!k) return MapPin;
  const table = field === "source" ? SOURCE_ICONS : CATEGORY_ICONS;
  return table[k] ?? MapPin;
}

/** Display label for a `source` / `category` value. */
export function labelFor(field: Field, value: string): string {
  const label = field === "source" ? SOURCE_LABELS[value.toLowerCase()] : undefined;
  return label ?? humanize(value).replace(/^\w/, (c) => c.toUpperCase());
}

/** Fixed display colour for a `source` / `category` value. */
export function colorFor(field: Field, value: string | null | undefined): string {
  const k = key(value);
  if (!k) return FALLBACK_COLOR;
  const table = field === "source" ? SOURCE_COLORS : CATEGORY_COLORS;
  return table[k] ?? FALLBACK_COLOR;
}

/**
 * Bare glyph. A stable module-scope component so callers don't create a
 * component during render (`react-hooks/static-components`).
 */
export function MarkerIcon({
  field,
  value,
  className,
  style,
}: {
  field: Field;
  value: string | null | undefined;
  className?: string;
  style?: CSSProperties;
}) {
  return createElement(iconFor(field, value), { className, style, strokeWidth: 2.5 });
}

/**
 * A filled circular pin -- the glyph in white on a disc of the value's colour,
 * with a white ring and drop shadow. Reads on any basemap (light, dark,
 * satellite) where a bare stroked glyph or a translucent circle disappears.
 */
export function LocationPin({
  field,
  value,
  size = 26,
  className,
}: {
  field: Field;
  value: string | null | undefined;
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "flex items-center justify-center rounded-full border-2 border-white",
        "shadow-[0_1px_4px_rgba(0,0,0,0.55)]",
        className,
      )}
      style={{ width: size, height: size, backgroundColor: colorFor(field, value) }}
    >
      <MarkerIcon
        field={field}
        value={value}
        className="text-white"
        style={{ width: Math.round(size * 0.52), height: Math.round(size * 0.52) }}
      />
    </span>
  );
}
