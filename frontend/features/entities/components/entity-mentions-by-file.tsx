"use client";

import { EntityMentionText } from "@/features/entities/components/entity-mention-text";
import { useEntityMentions } from "@/features/entities/hooks/use-entities";
import { useFile } from "@/features/files/api";
import { ChevronDown, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

interface FileGroup {
  fileId: string;
  datasetId?: string;
  count: number;
  firstOffset?: number;
}

function FileRow({ group }: { group: FileGroup }) {
  const [open, setOpen] = useState(false);
  const isUnknown = group.fileId === "unknown";
  const { data: file } = useFile(isUnknown ? undefined : group.fileId);
  const label = file?.filename ?? `file ${group.fileId.slice(0, 8)}`;
  const datasetId = group.datasetId ?? file?.datasetId ?? "";

  return (
    <li className="overflow-hidden rounded-lg border border-border">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs hover:bg-muted/30"
      >
        <span className="min-w-0 truncate">
          <span
            className={
              file
                ? "font-medium text-foreground"
                : "font-mono text-muted-foreground"
            }
          >
            {label}
          </span>
          <span className="ml-2 text-muted-foreground">
            {group.count} mention{group.count > 1 ? "s" : ""}
          </span>
        </span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && !isUnknown && (
        <div className="max-h-96 overflow-auto border-t border-border bg-background">
          <EntityMentionText
            fileId={group.fileId}
            datasetId={datasetId}
            focusOffset={group.firstOffset}
          />
        </div>
      )}
    </li>
  );
}

/**
 * Mentions of an entity grouped by the file they appear in, newest first, each
 * expanding to the highlighted source text. Shared by the entity and person
 * dossier pages; resolves the dataset per file so it works for dataset-agnostic
 * bridge entities too.
 */
export function EntityMentionsByFile({
  entityId,
  emptyLabel,
}: {
  entityId: string;
  emptyLabel?: string;
}) {
  const { data, isPending } = useEntityMentions(entityId);

  const byFile = useMemo(() => {
    const groups = new Map<string, FileGroup>();
    for (const m of data?.data ?? []) {
      const key = m.fileId ?? "unknown";
      const g =
        groups.get(key) ??
        ({
          fileId: key,
          datasetId: m.datasetId ?? undefined,
          count: 0,
          firstOffset: m.startOffset ?? undefined,
        } as FileGroup);
      g.count += 1;
      if (g.firstOffset == null && m.startOffset != null)
        g.firstOffset = m.startOffset;
      groups.set(key, g);
    }
    return [...groups.values()];
  }, [data]);

  if (isPending) {
    return <Loader2 size={16} className="animate-spin text-muted-foreground" />;
  }
  if (byFile.length === 0) {
    return (
      <p className="text-[11px] italic text-muted-foreground">
        {emptyLabel ?? "No mentions recorded yet."}
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {byFile.map((g) => (
        <FileRow key={g.fileId} group={g} />
      ))}
    </ul>
  );
}
