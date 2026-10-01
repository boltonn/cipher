import type { GraphNodeType, SelectorType } from "@/features/entities/types";
import {
  AtSign,
  Bitcoin,
  Building2,
  CalendarDays,
  Car,
  Globe,
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
} from "lucide";

/**
 * Renders the entity-type glyph as an inline `data:` SVG badge (a filled disc in
 * the type colour with the icon stroked on top). Fed to sigma's WebGL node-image
 * program via each node's `image` attribute, which replaces the old per-node
 * HTML `<span>` overlay -- it scales to any node count and survives pan/zoom for
 * free.
 */

type LucideNode = readonly (readonly [string, Record<string, string | number>])[];

const ENTITY_ICON: Record<GraphNodeType, LucideNode> = {
  event: CalendarDays as LucideNode,
  person: User as LucideNode,
  organization: Building2 as LucideNode,
  location: MapPin as LucideNode,
  selector: Fingerprint as LucideNode,
};

const SELECTOR_ICON: Record<SelectorType, LucideNode> = {
  phone: Phone as LucideNode,
  email: Mail as LucideNode,
  ip: Network as LucideNode,
  iban: Landmark as LucideNode,
  bank_card: CreditCard as LucideNode,
  passport: IdCard as LucideNode,
  national_id: IdCard as LucideNode,
  imei: Smartphone as LucideNode,
  imsi: Smartphone as LucideNode,
  social_handle: AtSign as LucideNode,
  crypto_address: Bitcoin as LucideNode,
  license_plate: Car as LucideNode,
  domain: Globe as LucideNode,
};

function iconMarkup(node: LucideNode): string {
  return node
    .map(([tag, attrs]) => {
      const a = Object.entries(attrs)
        .filter(([k]) => k !== "key")
        .map(([k, v]) => `${k}="${v}"`)
        .join(" ");
      return `<${tag} ${a}/>`;
    })
    .join("");
}

function badge(node: LucideNode): string {
  // A transparent-background glyph (dark halo + white stroke) so it stays legible
  // on any disc colour. The disc itself is painted by sigma from the node's
  // `color` attribute (drawingMode "background"), which the canvas reducer swaps
  // for the type / community palette -- so the colour is NOT baked in here.
  // Explicit width/height are required: @sigma/node-image's SVG loader throws
  // "cannot use `size` if target SVG has no definite dimensions" without them.
  const paths = iconMarkup(node);
  const glyph = (stroke: string, w: number) =>
    `<g transform="translate(22 22) scale(2.33)" fill="none" stroke="${stroke}" ` +
    `stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${paths}</g>`;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">` +
    glyph("#0b0b0f", 3.4) +
    glyph("#ffffff", 2) +
    `</svg>`;
  return `data:image/svg+xml;base64,${btoa(svg)}`;
}

/**
 * Best-effort selector kind from its display name (the normalized value). The
 * graph endpoint's nodes are bare `EntitySummary` with no `selectorType`, so a
 * phone reads as a phone / an email as an envelope without a round-trip. Returns
 * null when nothing matches -> the generic fingerprint.
 */
export function guessSelectorType(displayName: string): SelectorType | null {
  const v = displayName.trim();
  if (/^@[\w.]{2,}$/.test(v)) return "social_handle";
  if (/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v)) return "email";
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(v)) return "ip";
  if (/^[0-9a-f]{1,4}(:[0-9a-f]{0,4}){2,7}$/i.test(v)) return "ip";
  if (/^(0x[a-fA-F0-9]{40}|bc1[a-z0-9]{20,80}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|4[0-9AB][0-9A-Za-z]{93})$/.test(v))
    return "crypto_address";
  if (/^[A-Z]{2}\d{2}[A-Z0-9]{8,30}$/i.test(v)) return "iban";
  if (/^\d{15}$/.test(v)) return "imei";
  const digits = v.replace(/[\s().+-]/g, "");
  if (/^\+?[\d\s().-]{6,18}$/.test(v) && digits.length >= 7 && digits.length <= 15)
    return "phone";
  return null;
}

const cache = new Map<string, string>();

/** Cached transparent-glyph `data:` SVG URL for an entity node's WebGL image. */
export function nodeGlyphUrl(
  entityType: GraphNodeType,
  selectorType?: SelectorType | null
): string {
  const key = selectorType ? `${entityType}:${selectorType}` : entityType;
  const hit = cache.get(key);
  if (hit) return hit;
  const node =
    entityType === "selector" && selectorType
      ? SELECTOR_ICON[selectorType]
      : ENTITY_ICON[entityType];
  const url = badge(node);
  cache.set(key, url);
  return url;
}
