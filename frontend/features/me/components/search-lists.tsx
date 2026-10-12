"use client";

import { Button } from "@/components/ui/button";
import { useSearchHistory, useSetSearchSaved } from "@/features/global-search/api";
import type { SearchRecord } from "@/features/global-search/types";
import { formatDistanceToNow, parseISO } from "date-fns";
import { History, Star } from "lucide-react";
import Link from "next/link";

function SearchRow({ record }: { record: SearchRecord }) {
  const setSaved = useSetSearchSaved();
  const isSaved = !!record.dateSaved;
  const label = record.name || record.query || "Filtered browse";
  const Icon = isSaved ? Star : History;

  return (
    <li className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted">
      <Icon className={isSaved ? "size-3.5 fill-primary text-primary" : "size-3.5 text-muted-foreground"} />
      <Link href={`/search/${record.id}`} className="min-w-0 flex-1">
        <span className="block truncate text-sm text-foreground">{label}</span>
        {record.name && record.query && (
          <span className="block truncate text-xs text-muted-foreground">{record.query}</span>
        )}
      </Link>
      <span className="shrink-0 text-xs text-muted-foreground">
        {formatDistanceToNow(parseISO(record.dateLastRun), { addSuffix: true })}
      </span>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        disabled={setSaved.isPending}
        onClick={() => setSaved.mutate({ searchId: record.id, saved: !isSaved })}
      >
        {isSaved ? "Unsave" : "Save"}
      </Button>
    </li>
  );
}

/** Your saved searches (kept past pruning), or your recent unsaved ones. */
export function SearchList({ saved, limit }: { saved: boolean; limit: number }) {
  const { data, isPending } = useSearchHistory(limit, true, saved);
  if (isPending) return <p className="px-2 text-sm text-muted-foreground">Loading…</p>;
  if (!data?.data.length) {
    return (
      <p className="px-2 text-sm text-muted-foreground">
        {saved ? "Nothing saved yet — use Save search on a results page." : "No searches yet."}
      </p>
    );
  }
  return (
    <ul className="space-y-0.5">
      {data.data.map((record) => (
        <SearchRow key={record.id} record={record} />
      ))}
    </ul>
  );
}
