"use client";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { useDatasetScope } from "@/features/datasets/hooks/use-selected-datasets";
import {
  useEvents,
  useEventsCalendar,
  useMarkEventsInvalid,
} from "@/features/events/api";
import { EventDetailSheet } from "@/features/events/components/event-detail-sheet";
import { EventFiltersBar } from "@/features/events/components/event-filters";
import {
  EventsCalendar,
  monthGridRange,
} from "@/features/events/components/events-calendar";
import { EventsTable } from "@/features/events/components/events-table";
import {
  EMPTY_EVENT_FILTERS,
  type EventFilters,
  type EventSortField,
  type SortOrder,
} from "@/features/events/types";
import { startOfMonth } from "date-fns";
import {
  CalendarDays,
  CalendarRange,
  Search,
  Table2,
  Trash2,
  X,
} from "lucide-react";
import { readHandoff } from "@/features/global-search/handoff";
import { useState } from "react";

const LIMIT = 25;

export default function EventsPage() {
  const { datasetIds, setDatasetIds } = useDatasetScope();
  const [view, setView] = useState<"calendar" | "table">("table");
  const [query, setQuery] = useState(() => readHandoff("events")?.query ?? "");
  const [filters, setFilters] = useState<EventFilters>(EMPTY_EVENT_FILTERS);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ by: EventSortField; order: SortOrder }>({
    by: "dateStart",
    order: "asc",
  });
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [monthSeeded, setMonthSeeded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const markInvalid = useMarkEventsInvalid(() => setCheckedIds(new Set()));

  const resetPage = () => setPage(1);

  const listQuery = useEvents({
    datasetIds,
    query: query || undefined,
    ...filters,
    sortBy: sort.by,
    sortOrder: sort.order,
    page,
    limit: LIMIT,
  });

  const range = monthGridRange(month);
  const calendarQuery = useEventsCalendar({
    datasetIds,
    query: query || undefined,
    ...filters,
    dateFrom: range.from,
    dateTo: range.to,
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

  const changeSort = (by: EventSortField) => {
    setSort((prev) =>
      prev.by === by
        ? { by, order: prev.order === "asc" ? "desc" : "asc" }
        : { by, order: "asc" }
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
    !!filters.participants?.length ||
    !!filters.places?.length ||
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
        value={
          listQuery.data
            ? `${total.toLocaleString()} ${total === 1 ? "event" : "events"}`
            : undefined
        }
        icon={<CalendarDays size={13} className="text-primary/70" />}
        actions={
          <DatasetSelect
            datasetIds={datasetIds}
            placeholder="All datasets"
            onChange={(ids) => {
              setDatasetIds(ids);
              resetPage();
            }}
          />
        }
      />

      <div className="mt-4">
        <Tabs
          value={view}
          onValueChange={(v) => setView(v as "calendar" | "table")}
          className="gap-4"
        >
          <div className="flex items-center gap-2">
            <div className="flex-1">
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
            </div>
            <TabsList className="h-10">
              <TabsTrigger value="calendar" className="gap-1.5 px-3 text-xs">
                <CalendarRange size={13} />
                Calendar
              </TabsTrigger>
              <TabsTrigger value="table" className="gap-1.5 px-3 text-xs">
                <Table2 size={13} />
                Table
              </TabsTrigger>
            </TabsList>
          </div>

          <EventFiltersBar
            value={filters}
            onChange={(next) => {
              setFilters(next);
              resetPage();
            }}
            query={query}
            onClearQuery={() => {
              setQuery("");
              resetPage();
            }}
            onClear={clearAll}
            datasetIds={datasetIds}
            showDateRange={view === "table"}
          />

          <TabsContent value="calendar">
            <EventsCalendar
              monthStart={month}
              onMonthChange={setMonth}
              datasetIds={datasetIds}
              events={calendarQuery.data ?? []}
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
                {checkedIds.size > 0 && (
                  <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-1.5 text-[11px]">
                    <b className="text-foreground">
                      {checkedIds.size.toLocaleString()} selected
                    </b>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 gap-1 px-2 text-[11px]"
                      onClick={() => setCheckedIds(new Set())}
                      disabled={markInvalid.isPending}
                    >
                      <X size={11} /> Clear
                    </Button>
                    <div className="ml-auto">
                      <ConfirmDialog
                        trigger={
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 gap-1 px-2 text-[11px] text-destructive hover:text-destructive"
                          >
                            <Trash2 size={11} /> Mark invalid
                          </Button>
                        }
                        title={`Mark ${checkedIds.size.toLocaleString()} ${checkedIds.size === 1 ? "event" : "events"} invalid?`}
                        description="Not real events — they are deleted along with their participants and places. The source files are kept."
                        confirmLabel="Mark invalid"
                        onConfirm={() => markInvalid.mutate([...checkedIds])}
                        isPending={markInvalid.isPending}
                      />
                    </div>
                  </div>
                )}
                <EventsTable
                  events={events}
                  sortBy={sort.by}
                  sortOrder={sort.order}
                  onSortChange={changeSort}
                  onFilter={(patch) => {
                    setFilters((prev) => ({ ...prev, ...patch }));
                    resetPage();
                  }}
                  onSelect={(e) => setSelectedId(e.id)}
                  checkedIds={checkedIds}
                  onCheckedIdsChange={setCheckedIds}
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
