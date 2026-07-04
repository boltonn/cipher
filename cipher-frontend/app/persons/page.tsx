"use client";

import { Pagination } from "@/components/pagination";
import { PageHeader } from "@/components/page-header";
import { SearchBarShell } from "@/components/search-bar-shell";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { CreatePersonDialog } from "@/features/persons/components/create-person-dialog";
import { PersonCard } from "@/features/persons/components/person-card";
import { usePersonSearch } from "@/features/persons/hooks/use-persons";
import { useDebounce } from "@/hooks/use-debounce";
import { BadgeCheck, Loader2, Plus, Search, UserRound } from "lucide-react";
import { useState } from "react";

const LIMIT = 24;

export default function PersonsPage() {
  const [query, setQuery] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const debouncedQuery = useDebounce(query, 300);

  const { data, isPending, isFetching } = usePersonSearch({
    query: debouncedQuery || undefined,
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
            className="bg-indigo-600 hover:bg-indigo-500 gap-2 h-9 text-[10px] font-bold uppercase tracking-widest"
          >
            <Plus size={14} />
            New Person
          </Button>
        }
      />

      <div className="mt-4">
        <SearchBarShell isActive={isFetching} icon={<Search size={18} strokeWidth={1.5} />}>
          <input
            aria-label="Search persons"
            type="text"
            autoComplete="off"
            placeholder="Search by name..."
            className="w-full bg-transparent py-4 px-4 text-slate-100 placeholder:text-slate-600 focus:outline-none text-sm tracking-wide"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />

          <div className="flex items-center gap-2 shrink-0 pr-1">
            <BadgeCheck size={14} className="text-indigo-400" />
            <span className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">
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
          <div className="flex flex-col items-center justify-center py-48 text-slate-500">
            <Loader2 className="h-10 w-10 animate-spin text-indigo-500/30 mb-4" />
          </div>
        ) : persons.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-40 border border-dashed border-white/5 rounded-3xl bg-slate-900/10">
            <UserRound size={28} className="text-slate-700 mb-3" />
            <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-slate-600">
              No People Found
            </p>
          </div>
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
