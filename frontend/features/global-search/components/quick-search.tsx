"use client";

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useSelectedDatasets } from "@/features/datasets/hooks/use-selected-datasets";
import { NAV } from "@/lib/nav";
import { History, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useRunSearch, useSearchHistory } from "../api";
import { EMPTY_FILTERS } from "../hooks/use-search-actions";

const PAGES = [NAV.home, ...NAV.find, ...NAV.knowledge, ...NAV.manage, NAV.graph, ...NAV.help].flatMap((item) => [
  item,
  ...(item.children ?? []),
]);

/**
 * Ctrl/⌘+K from any page: type and press Enter to search everything, or jump to a page or a recent
 * search. Matching is local while you type (no request per keystroke); Enter runs the real search.
 */
export function QuickSearch() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const { datasetIds } = useSelectedDatasets();
  const router = useRouter();
  const runSearch = useRunSearch();
  const { data: history } = useSearchHistory(8, open);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const close = () => {
    setOpen(false);
    setValue("");
  };
  const searchEverything = () => {
    if (!value.trim()) return;
    runSearch.mutate({ query: value.trim(), datasetIds, filters: EMPTY_FILTERS });
    close();
  };
  const go = (href: string) => {
    router.push(href);
    close();
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={(next) => (next ? setOpen(true) : close())}
      title="Quick search"
      description="Search everything, or jump to a page or a recent search"
    >
      <Command>
        <CommandInput value={value} onValueChange={setValue} placeholder="Search everything, or jump to…" />
        <CommandList>
          <CommandEmpty>Press Enter to search everything.</CommandEmpty>
          {value.trim() && (
            <CommandGroup forceMount>
              <CommandItem forceMount value={`search-everything ${value}`} onSelect={searchEverything}>
                <Search />
                <span>
                  Search everything for <span className="font-medium">“{value.trim()}”</span>
                </span>
              </CommandItem>
            </CommandGroup>
          )}
          {!!history?.data.length && (
            <CommandGroup heading="Recent searches">
              {history.data
                .filter((record) => record.query)
                .map((record) => (
                  <CommandItem key={record.id} value={`recent ${record.query} ${record.id}`} onSelect={() => go(`/search/${record.id}`)}>
                    <History />
                    <span className="truncate">{record.query}</span>
                  </CommandItem>
                ))}
            </CommandGroup>
          )}
          <CommandGroup heading="Go to">
            {PAGES.map((page) => (
              <CommandItem key={page.url} value={`page ${page.title}`} onSelect={() => go(page.url)}>
                <page.icon />
                <span>{page.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
