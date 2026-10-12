"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Star } from "lucide-react";
import { useState } from "react";
import { useSearchRecord, useSetSearchSaved } from "../api";

/** Save this search under a name (kept past pruning, listed on My work), or unsave it. */
export function SaveSearchButton({ searchId, query }: { searchId: string; query: string }) {
  const { data: record } = useSearchRecord(searchId);
  const setSaved = useSetSearchSaved();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const isSaved = !!record?.dateSaved;

  if (isSaved) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled={setSaved.isPending}
        onClick={() => setSaved.mutate({ searchId, saved: false })}
        title="Unsave"
      >
        <Star className="size-3.5 fill-primary text-primary" />
        {record?.name || "Saved"}
      </Button>
    );
  }

  const save = () =>
    setSaved.mutate({ searchId, saved: true, name: name.trim() || null }, { onSuccess: () => setOpen(false) });

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setName(query);
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" disabled={!record}>
          <Star className="size-3.5" />
          Save search
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 space-y-2">
        <p className="text-xs text-muted-foreground">Name (optional)</p>
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && save()}
          autoComplete="off"
          className="h-8 text-sm"
        />
        <Button size="sm" className="w-full" onClick={save} disabled={setSaved.isPending}>
          Save
        </Button>
      </PopoverContent>
    </Popover>
  );
}
