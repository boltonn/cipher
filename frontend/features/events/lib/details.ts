/**
 * Editable fields for an event's typed `details` blob, mirroring the backend
 * discriminated union `cipher.schemas.graph.event.{Travel,Lodging,Reservation,
 * Delivery}Details`. `meeting` / `gathering` / `other` carry no detail row.
 */
import type { EventType } from "@/features/events/types";

export type DetailFieldKind = "text" | "int" | "number" | "select";

export interface DetailField {
  name: string;
  label: string;
  kind: DetailFieldKind;
  /** for kind === "select" */
  options?: readonly string[];
}

export const DETAIL_FIELDS: Partial<Record<EventType, readonly DetailField[]>> = {
  travel: [
    {
      name: "mode",
      label: "Mode",
      kind: "select",
      options: ["flight", "train", "bus", "ferry", "car_rental", "other"] as const,
    },
    { name: "operator", label: "Operator", kind: "text" },
    { name: "number", label: "Number", kind: "text" },
    { name: "confirmation", label: "Confirmation", kind: "text" },
  ],
  lodging: [
    { name: "operator", label: "Operator", kind: "text" },
    { name: "confirmation", label: "Confirmation", kind: "text" },
    { name: "nights", label: "Nights", kind: "int" },
    { name: "guests", label: "Guests", kind: "int" },
  ],
  reservation: [
    { name: "operator", label: "Provider", kind: "text" },
    { name: "confirmation", label: "Confirmation", kind: "text" },
    { name: "party_size", label: "Party size", kind: "int" },
  ],
  delivery: [
    { name: "carrier", label: "Carrier", kind: "text" },
    { name: "tracking_number", label: "Tracking number", kind: "text" },
    { name: "order_number", label: "Order number", kind: "text" },
  ],
};

export function detailFieldsFor(type: EventType): readonly DetailField[] {
  return DETAIL_FIELDS[type] ?? [];
}

/** Form string values → the `details` object the API expects, or null when empty. */
export function buildDetails(
  type: EventType,
  values: Record<string, string>
): Record<string, unknown> | null {
  const fields = detailFieldsFor(type);
  if (fields.length === 0) return null;

  const out: Record<string, unknown> = { kind: type };
  let hasValue = false;
  for (const f of fields) {
    const raw = (values[f.name] ?? "").trim();
    if (!raw) continue;
    if (f.kind === "int") {
      const n = Number.parseInt(raw, 10);
      if (Number.isNaN(n)) continue;
      out[f.name] = n;
    } else if (f.kind === "number") {
      const n = Number.parseFloat(raw);
      if (Number.isNaN(n)) continue;
      out[f.name] = n;
    } else {
      out[f.name] = raw;
    }
    hasValue = true;
  }
  return hasValue ? out : null;
}

/** Existing `details` object → flat string values for the form inputs. */
export function detailsToFormValues(
  details: Record<string, unknown> | null | undefined
): Record<string, string> {
  const values: Record<string, string> = {};
  if (!details) return values;
  for (const [k, v] of Object.entries(details)) {
    if (k === "kind" || v == null) continue;
    values[k] = String(v);
  }
  return values;
}
