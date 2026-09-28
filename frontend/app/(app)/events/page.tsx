"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { useEvents, useEventsCalendar } from "@/features/events/api";
import { EventDetailSheet } from "@/features/events/components/event-detail-sheet";
import { EventFiltersBar } from "@/features/events/components/event-filters";
import { EventsCalendar, monthGridRange } from "@/features/events/components/events-calendar";
import { EventsTable } from "@/features/events/components/events-table";
import { matchesEventFilters } from "@/features/events/lib/filter";
import {
  EMPTY_EVENT_FILTERS,
  type EventFilters,
  type EventSortField,
  type SortOrder,
} from "@/features/events/types";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import { startOfMonth } from "date-fns";
import { CalendarDays, CalendarRange, Search, Table2 } from "lucide-react";
import { useMemo, useState } from "react";

const LIMIT = 25;

export default function EventsPage() {
  const [datasetId, setDatasetId] = useLocalStorageState<string | undefined>(
    "events:datasetId",
    undefined
  );
  const [view, setView] = useLocalStorageState<"calendar" | "table">(
    "events:view",
    "table"
  );
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<EventFilters>(EMPTY_EVENT_FILTERS);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ by: EventSortField; order: SortOrder }>({
    by: "date_start",
    order: "asc",
  });
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [monthSeeded, setMonthSeeded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const resetPage = () => setPage(1);

  const listQuery = useEvents({
    datasetId,
    query: query || undefined,
    ...filters,
    sortBy: sort.by,
    sortOrder: sort.order,
    page,
    limit: LIMIT,
  });

  const range = monthGridRange(month);
  const calendarQuery = useEventsCalendar({
    dateFrom: range.from,
    dateTo: range.to,
    datasetId,
  });

  const events = listQuery.data?.data ?? [];
  const total = listQuery.data?.total ?? 0;

  // On first load: if the current month's calendar grid is empty, open the
  // calendar on the earliest event's month instead of a blank current month.
  // One-shot ("adjust state during render", not an effect); manual month nav
  // and later loads are untouched.
  if (!monthSeeded && listQuery.data && calendarQuery.data) {
    setMonthSeeded(true);
    const earliest = listQuery.data.data[0]?.dateStart;
    if (calendarQuery.data.length === 0 && earliest) {
      setMonth(startOfMonth(new Date(earliest)));
    }
  }

  // `/events/calendar` only takes a date window; narrow type/status/verified +
  // the title query here so the shared filter bar drives both views.
  const calendarEvents = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (calendarQuery.data ?? []).filter(
      (e) =>
        matchesEventFilters(e, filters) &&
        (!q || e.title.toLowerCase().includes(q))
    );
  }, [calendarQuery.data, filters, query]);

  const changeSort = (by: EventSortField) => {
    setSort((prev) =>
      prev.by === by ? { by, order: prev.order === "asc" ? "desc" : "asc" } : { by, order: "asc" }
    );
    resetPage();
  };

  const clearAll = () => {
    setQuery("");
    setFilters({ ...EMPTY_EVENT_FILTERS });
    resetPage();
  };

  const refined =
    !!query ||
    !!filters.eventType ||
    !!filters.category ||
    !!filters.status ||
    filters.isVerified != null ||
    !!filters.dateFrom ||
    !!filters.dateTo;

  return (
    <div className="relative mx-auto max-w-400 px-6 pb-20">
      <PageHeader
        eyebrow="Events"
        value={`${total.toLocaleString()} events${datasetId ? " · 1 dataset" : ""}`}
        icon={<CalendarDays size={13} className="text-primary/70" />}
        actions={
          <DatasetSelect
            datasetId={datasetId}
            onChange={(id) => {
              setDatasetId(id);
              resetPage();
            }}
          />
        }
      />

      <div className="mt-4 space-y-4">
        <SearchBarShell
          isActive={listQuery.isFetching || calendarQuery.isFetching}
          icon={<Search size={18} strokeWidth={1.5} />}
        >
          <SearchInput
            value={query}
            onSearch={(q) => {
              setQuery(q);
              resetPage();
            }}
            ariaLabel="Search events"
            placeholder="Search event titles…"
          />
        </SearchBarShell>

        <EventFiltersBar
          value={filters}
          onChange={(next) => {
            setFilters(next);
            resetPage();
          }}
          queryActive={!!query}
          onClear={clearAll}
          datasetId={datasetId}
          showDateRange={view === "table"}
        />

        <Tabs
          value={view}
          onValueChange={(v) => setView(v as "calendar" | "table")}
          className="gap-4"
        >
          <TabsList className="h-9">
            <TabsTrigger value="calendar" className="gap-1.5 px-3 text-xs">
              <CalendarRange size={13} />
              Calendar
            </TabsTrigger>
            <TabsTrigger value="table" className="gap-1.5 px-3 text-xs">
              <Table2 size={13} />
              Table
            </TabsTrigger>
          </TabsList>

          <TabsContent value="calendar">
            <EventsCalendar
              monthStart={month}
              onMonthChange={setMonth}
              events={calendarEvents}
              onSelect={(e) => setSelectedId(e.id)}
              isLoading={calendarQuery.isFetching}
            />
          </TabsContent>

          <TabsContent value="table" className="space-y-4">
            {listQuery.isPending ? (
              <PageLoading className="py-24" label="Loading events…" />
            ) : events.length === 0 ? (
              <EmptyState
                icon={CalendarDays}
                title={refined ? "No matches" : "No events yet"}
                body={
                  refined
                    ? "Nothing matches the current search and filters."
                    : "Run `cipher extract-events` (calendar files) or `extract-events --llm` (email bodies) to pull events out of a dataset."
                }
              />
            ) : (
              <>
                <EventsTable
                  events={events}
                  sortBy={sort.by}
                  sortOrder={sort.order}
                  onSortChange={changeSort}
                  onSelect={(e) => setSelectedId(e.id)}
                />
                <Pagination
                  currentPage={page}
                  totalItems={total}
                  itemsPerPage={LIMIT}
                  onPageChange={setPage}
                  isLoading={listQuery.isFetching}
                />
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>

      <EventDetailSheet
        eventId={selectedId}
        onOpenChange={(open) => !open && setSelectedId(null)}
      />
    </div>
  );
}
