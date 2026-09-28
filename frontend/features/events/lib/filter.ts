import type { CipherEvent, EventFilters } from "@/features/events/types";

/**
 * Client-side application of the shared filter bar. Used for the calendar view,
 * whose `/events/calendar` feed only takes a date window — type / status /
 * verified are narrowed here so the same bar drives both views.
 */
export function matchesEventFilters(event: CipherEvent, filters: EventFilters): boolean {
  if (filters.eventType && event.eventType !== filters.eventType) return false;
  if (
    filters.category &&
    !event.categories.some((c) => c.toLowerCase() === filters.category!.toLowerCase())
  )
    return false;
  if (filters.status && event.status !== filters.status) return false;
  if (filters.isVerified != null && event.isVerified !== filters.isVerified) return false;
  return true;
}
