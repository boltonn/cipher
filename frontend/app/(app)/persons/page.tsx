"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Switch } from "@/components/ui/switch";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { PersonCard } from "@/features/persons/components/person-card";
import { PersonsTable } from "@/features/persons/components/persons-table";
import { usePersonSearch } from "@/features/persons/hooks/use-persons";
import { cn } from "@/lib/utils";
import { BadgeCheck, LayoutGrid, Plus, Search, Table2, UserRound } from "lucide-react";
import { useState } from "react";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";

const LIMIT = 24;

type PersonsView = "grid" | "table";

export default function PersonsPage() {
  const [query, setQuery] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [view, setView] = useLocalStorageState<PersonsView>(
    "persons:view",
    "grid"
  );

  const { data, isPending, isFetching, isError, refetch } = usePersonSearch({
    query: query || undefined,
    isVerified: verifiedOnly || undefined,
    limit: LIMIT,
    page,
  });

  const persons = data?.data ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20 pt-5">
      <PageHeader
        eyebrow="Persons"
        value={`${total.toLocaleString()} ${total === 1 ? "person" : "people"}`}
        actions={
          <>
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
              <Plus size={14} />
              New Person
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
              setPage(1);
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
                setPage(1);
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
              <PersonsTable persons={persons} />
            ) : (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {persons.map((person) => (
                  <PersonCard key={person.id} person={person} />
                ))}
              </div>
            )}

            <Pagination
              currentPage={page}
              totalItems={total}
              itemsPerPage={LIMIT}
              onPageChange={setPage}
              isLoading={isFetching}
              siblingCount={2}
            />
          </div>
        )}
      </main>

      <CreatePersonDialog isOpen={isCreateOpen} onOpenChange={setIsCreateOpen} />
    </div>
  );
}
