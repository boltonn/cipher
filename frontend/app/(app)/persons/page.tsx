"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SelectionBar } from "@/components/selection-bar";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { MergePersonsDialog } from "@/features/persons/components/merge-persons-dialog";
import { PersonCard } from "@/features/persons/components/person-card";
import { PersonsTable } from "@/features/persons/components/persons-table";
import { usePersonSearch } from "@/features/persons/hooks/use-persons";
import type { PersonSortFieldType } from "@/features/persons/types";
import { cn } from "@/lib/utils";
import { ArrowDownWideNarrow, BadgeCheck, LayoutGrid, Merge, Search, Table2, UserRound, UserRoundPlus } from "lucide-react";
import { useState } from "react";
import { useGridSelection } from "@/hooks/use-grid-selection";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";

const LIMIT = 42; // fills whole rows at 6 and 7 columns

type PersonsView = "grid" | "table";

const SORTS: { value: PersonSortFieldType; label: string }[] = [
  { value: "relevance", label: "Most relevant" },
  { value: "name", label: "Name" },
  { value: "dateUpdated", label: "Recently updated" },
];

export default function PersonsPage() {
  const [query, setQuery] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [sortBy, setSortBy] = useState<PersonSortFieldType>("relevance");
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isMergeOpen, setIsMergeOpen] = useState(false);
  const selection = useGridSelection();
  const [view, setView] = useLocalStorageState<PersonsView>(
    "persons:view",
    "grid"
  );

  const { data, isPending, isFetching, isError, refetch } = usePersonSearch({
    query: query || undefined,
    isVerified: verifiedOnly || undefined,
    sortBy,
    sortOrder: sortBy === "name" ? "asc" : "desc",
    limit: LIMIT,
    page,
  });

  const sortLabel = SORTS.find((sort) => sort.value === sortBy)?.label;
  const persons = data?.data ?? [];
  const total = data?.total ?? 0;
  const personIds = persons.map((p) => p.id);
  const selectedPersons = persons.filter((p) => selection.selectedIds.has(p.id));

  // selection is page-scoped: any change to the result set clears it
  const resetPage = () => {
    setPage(1);
    selection.clear();
  };

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20 pt-5">
      <PageHeader
        eyebrow="Persons"
        value={`${total.toLocaleString()} ${total === 1 ? "person" : "people"}`}
        actions={
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label={`Sort: ${sortLabel}`}
                  title={`Sort: ${sortLabel}`}
                  className={cn(
                    "h-9 w-9 border-border bg-muted/40",
                    sortBy === "relevance"
                      ? "text-muted-foreground hover:text-foreground"
                      : "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                  )}
                >
                  <ArrowDownWideNarrow size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuLabel className="text-xs text-muted-foreground">Sort by</DropdownMenuLabel>
                <DropdownMenuRadioGroup
                  value={sortBy}
                  onValueChange={(value) => {
                    setSortBy(value as PersonSortFieldType);
                    resetPage();
                  }}
                >
                  {SORTS.map(({ value, label }) => (
                    <DropdownMenuRadioItem key={value} value={value} className="text-xs">
                      {label}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>

            <ButtonGroup>
              {(
                [
                  { mode: "grid", label: "Card view", Icon: LayoutGrid },
                  { mode: "table", label: "Table view", Icon: Table2 },
                ] as const
              ).map(({ mode, label, Icon }) => (
                <Button
                  key={mode}
                  variant="outline"
                  size="icon"
                  onClick={() => setView(mode)}
                  aria-label={label}
                  aria-pressed={view === mode}
                  className={cn(
                    "h-9 w-9 border-border bg-muted/40",
                    view === mode
                      ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon size={14} />
                </Button>
              ))}
            </ButtonGroup>

            <Button
              onClick={() => setIsCreateOpen(true)}
              className="bg-primary hover:bg-primary gap-2 h-9 text-xs font-medium"
            >
              <UserRoundPlus size={14} />
              New person
            </Button>
          </>
        }
      />

      <div className="mt-4">
        <SearchBarShell isActive={isFetching} icon={<Search size={18} strokeWidth={1.5} />}>
          <SearchInput
            ariaLabel="Search persons"
            placeholder="Search by name..."
            value={query}
            onSearch={(next) => {
              setQuery(next);
              resetPage();
            }}
          />

          <div className="flex items-center gap-2 shrink-0 pr-1">
            <BadgeCheck size={14} className="text-primary" />
            <span className="text-xs text-muted-foreground">
              Verified only
            </span>
            <Switch
              checked={verifiedOnly}
              onCheckedChange={(checked) => {
                setVerifiedOnly(checked);
                resetPage();
              }}
            />
          </div>
        </SearchBarShell>
      </div>

      <main className="mt-6">
        {isError ? (
          <PageError
            title="Couldn’t load people"
            body="The request failed. This is usually temporary — try again."
            onRetry={() => refetch()}
          />
        ) : isPending ? (
          <PageLoading icon={UserRound} label="Loading persons…" onRetry={() => refetch()} />
        ) : persons.length === 0 ? (
          <EmptyState
            icon={UserRound}
            title="No people found"
            body={
              query || verifiedOnly
                ? "No people match the current search and filters."
                : "Cluster faces into people, or create one manually with “New Person”."
            }
          />
        ) : (
          <div className="space-y-10">
            {view === "table" ? (
              <PersonsTable persons={persons} selection={selection} />
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7">
                {persons.map((person) => (
                  <PersonCard
                    key={person.id}
                    person={person}
                    isSelected={selection.selectedIds.has(person.id)}
                    isSelectionActive={selection.selectedIds.size > 0}
                    onToggleSelect={(id, range) => selection.toggle(id, personIds, range)}
                  />
                ))}
              </div>
            )}

            <Pagination
              currentPage={page}
              totalItems={total}
              itemsPerPage={LIMIT}
              onPageChange={(next) => {
                setPage(next);
                selection.clear();
              }}
              isLoading={isFetching}
              siblingCount={2}
            />
          </div>
        )}
      </main>

      <SelectionBar selection={selection} loadedIds={personIds}>
        <Button
          size="sm"
          className="h-7 gap-1 text-[11px]"
          disabled={selectedPersons.length < 2}
          title={selectedPersons.length < 2 ? "Select at least two people to merge" : undefined}
          onClick={() => setIsMergeOpen(true)}
        >
          <Merge size={12} />
          Merge
        </Button>
      </SelectionBar>

      <CreatePersonDialog isOpen={isCreateOpen} onOpenChange={setIsCreateOpen} />
      <MergePersonsDialog
        persons={selectedPersons}
        isOpen={isMergeOpen}
        onOpenChange={setIsMergeOpen}
        onMerged={selection.clear}
      />
    </div>
  );
}
