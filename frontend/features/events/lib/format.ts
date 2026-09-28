import type { CipherEvent } from "@/features/events/types";
import { format } from "date-fns";

/** Human date for one event, honouring `datePrecision` and `isAllDay`. */
export function formatEventStart(event: CipherEvent): string {
  const d = new Date(event.dateStart);
  switch (event.datePrecision) {
    case "year":
      return format(d, "yyyy");
    case "month":
      return format(d, "MMM yyyy");
    case "day":
    case "approximate":
      return format(d, "EEE, MMM d, yyyy");
    default:
      return event.isAllDay
        ? format(d, "EEE, MMM d, yyyy")
        : format(d, "EEE, MMM d, yyyy · h:mm a");
  }
}

/** Compact time for a calendar chip: `9:30a`, `all day`, or `~` for fuzzy dates. */
export function formatChipTime(event: CipherEvent): string {
  if (event.datePrecision === "month" || event.datePrecision === "year") return "~";
  if (event.isAllDay || event.datePrecision === "day") return "all day";
  return format(new Date(event.dateStart), "h:mmaaaaa'm'").replace("am", "a").replace("pm", "p");
}

export function formatDateRange(event: CipherEvent): string | null {
  if (!event.dateEnd) return null;
  const start = new Date(event.dateStart);
  const end = new Date(event.dateEnd);
  const sameDay = start.toDateString() === end.toDateString();
  if (event.isAllDay || event.datePrecision !== "exact") {
    return sameDay ? null : `${format(start, "MMM d")} – ${format(end, "MMM d, yyyy")}`;
  }
  return sameDay
    ? `${format(start, "h:mm a")} – ${format(end, "h:mm a")}`
    : `${format(start, "MMM d, h:mm a")} – ${format(end, "MMM d, h:mm a")}`;
}
