"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { PersonCard } from "@/features/persons/components/person-card";
import { usePersonSearch } from "@/features/persons/hooks/use-persons";
import { BadgeCheck, Plus, Search, UserRound } from "lucide-react";
import { useState } from "react";

const LIMIT = 24;

export default function PersonsPage() {
  const [query, setQuery] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const { data, isPending, isFetching } = usePersonSearch({
    query: query || undefined,
    isVerified: verifiedOnly || undefined,
    limit: LIMIT,
    page,
  });

  const persons = data?.data ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20">
      <PageHeader
        eyebrow="Persons"
        value={`${total.toLocaleString()} Results`}
        actions={
          <Button
            onClick={() => setIsCreateOpen(true)}
            className="bg-primary hover:bg-primary gap-2 h-9 text-[10px] font-bold uppercase tracking-widest"
          >
            <Plus size={14} />
            New Person
          </Button>
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
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
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
        {isPending ? (
          <PageLoading icon={UserRound} label="Loading persons…" />
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
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-4">
              {persons.map((person) => (
                <PersonCard key={person.id} person={person} />
              ))}
            </div>

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
