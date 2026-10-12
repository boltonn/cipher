"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { handOff, type ChunkSearchHandoff } from "@/features/global-search/handoff";
import { ChevronDown, ExternalLink } from "lucide-react";
import { useRouter } from "next/navigation";

/** What `search_passages` reports about one search (see backend `agent/tools.py`). */
export interface SearchRun {
  query: string | null;
  mode: string;
  total: number;
  promotionsAndSpamHidden: boolean;
  openAll: ChunkSearchHandoff & { query: string };
}

interface SearchSummaryProps {
  searches: SearchRun[];
  filesRead: number;
}

function searchLabel(search: SearchRun): string {
  const what = search.query ? `“${search.query}”` : "Browse";
  const about = search.openAll.graphExpandLabel ? ` · ${search.openAll.graphExpandLabel}` : "";
  return `${what}${about} · ${search.total.toLocaleString()}`;
}

/**
 * How much of the data an answer rests on: the searches run, how many files matched, how many
 * were read -- and every search can be opened in full on the text-search page, so the analyst
 * sees all the matches, not only the few the assistant cited.
 */
export function SearchSummary({ searches, filesRead }: SearchSummaryProps) {
  const router = useRouter();
  if (!searches.length) return null;
  const most = Math.max(...searches.map((search) => search.total));
  const open = (search: SearchRun) => {
    const { query, ...chunkSearch } = search.openAll;
    handOff({ target: "text", query, chunkSearch });
    router.push("/search/text");
  };
  const facts = [
    `${searches.length} search${searches.length === 1 ? "" : "es"}`,
    `${searches.length === 1 ? "" : "up to "}${most.toLocaleString()} file${most === 1 ? "" : "s"} matched`,
    `read ${filesRead} file${filesRead === 1 ? "" : "s"}`,
    searches.some((search) => search.promotionsAndSpamHidden) && "promotions and spam left out",
  ].filter(Boolean);

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
      <span>{facts.join(" · ")}</span>
      {searches.length === 1 ? (
        <Button variant="ghost" size="sm" className="h-6 gap-1 px-1.5 text-[11px]" onClick={() => open(searches[0])}>
          Open all in search
          <ExternalLink className="size-3" />
        </Button>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 gap-1 px-1.5 text-[11px]">
              Open a search in full
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-96 max-w-[calc(100vw-2rem)]">
            {searches.map((search, index) => (
              <DropdownMenuItem key={index} onSelect={() => open(search)} className="text-xs">
                <span className="truncate">{searchLabel(search)}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
