"use client";

import { Pagination } from "@/components/pagination";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SidebarTrigger } from "@/components/ui/sidebar";
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
      <div className="sticky top-0 z-30 flex items-center justify-between pt-6 pb-2 bg-[#050507]/90">
        <div className="flex items-center gap-4">
          <SidebarTrigger className="h-9 w-9 text-slate-400 hover:text-indigo-400" />
          <div className="flex flex-col">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
              Persons
            </span>
            <span className="text-xs font-mono text-indigo-400/80">
              {total.toLocaleString()} Results
            </span>
          </div>
        </div>

        <Button
          onClick={() => setIsCreateOpen(true)}
          className="bg-indigo-600 hover:bg-indigo-500 gap-2 h-9 text-[10px] font-bold uppercase tracking-widest"
        >
          <Plus size={14} />
          New Person
        </Button>
      </div>

      <div className="mt-4 flex items-center gap-4">
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
          />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search by name..."
            className="pl-9 bg-slate-900/40 border-white/10 text-sm h-10"
          />
        </div>

        <div className="flex items-center gap-2 shrink-0">
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
