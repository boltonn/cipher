"use client";

import {
  Autocomplete,
  AutocompleteContent,
  AutocompleteInput,
  AutocompleteItem,
} from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import { useTagFiles } from "@/features/files/api";
import { useTagNames } from "@/features/tags/hooks/use-tag-names";
import { Loader2, Tag, ThumbsUp } from "lucide-react";
import { useState } from "react";
import type { JudgedSource } from "../types";

interface RelevantSourcesBarProps {
  /** Sources the analyst marked relevant in this conversation. */
  sources: JudgedSource[];
  onClear: () => void;
}

/** Turn the sources marked relevant into a tagged set: one tag, every marked file, recorded as yours. */
export function RelevantSourcesBar({ sources, onClear }: RelevantSourcesBarProps) {
  const [tag, setTag] = useState("");
  const [tagged, setTagged] = useState<string | null>(null);
  const { data: names = [] } = useTagNames("content");
  const tagFiles = useTagFiles();
  const fileIds = [...new Set(sources.flatMap((source) => (source.fileId ? [source.fileId] : [])))];
  if (!sources.length) return null;

  const suggestions = names.filter((name) => name.toLowerCase().includes(tag.trim().toLowerCase())).slice(0, 8);
  const apply = (value: string) => {
    const name = value.trim();
    if (!name || !fileIds.length) return;
    tagFiles.mutate({ tag: name, fileIds }, { onSuccess: () => setTagged(name) });
  };

  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-1.5 text-xs">
      <ThumbsUp className="size-3.5 text-primary" />
      <span className="text-muted-foreground">
        {sources.length} source{sources.length === 1 ? "" : "s"} marked relevant
      </span>
      {fileIds.length > 0 && (
        <>
          <Tag className="ml-1 size-3.5 text-muted-foreground" />
          <Autocomplete className="w-44">
            <AutocompleteInput
              value={tag}
              onValueChange={(value) => {
                setTag(value);
                setTagged(null);
              }}
              onEnter={apply}
              placeholder="Tag their files as…"
              className="h-7"
            />
            {suggestions.length > 0 && (
              <AutocompleteContent>
                {suggestions.map((name) => (
                  <AutocompleteItem key={name} value={name} onSelect={() => setTag(name)}>
                    {name}
                  </AutocompleteItem>
                ))}
              </AutocompleteContent>
            )}
          </Autocomplete>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 px-2 text-xs"
            disabled={!tag.trim() || tagFiles.isPending}
            onClick={() => apply(tag)}
          >
            {tagFiles.isPending && <Loader2 className="size-3 animate-spin" />}
            Tag {fileIds.length} file{fileIds.length === 1 ? "" : "s"}
          </Button>
        </>
      )}
      {tagged && <span className="text-primary">Tagged “{tagged}”</span>}
      <Button type="button" size="sm" variant="ghost" className="ml-auto h-7 px-2 text-xs" onClick={onClear}>
        Clear marks
      </Button>
    </div>
  );
}
