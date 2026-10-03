"use client";

import { useFile, useSetFileTags } from "@/features/files/api";
import { ProvenanceTagsInput } from "@/features/tags/components/provenance-tags-input";
import { Tag } from "lucide-react";

/** A file's content tags (shared by every copy of the bytes), with who/what set each. */
export function FileTagsEditor({ fileId }: { fileId: string }) {
  const { data: file } = useFile(fileId);
  const setTags = useSetFileTags(fileId);
  if (!file) return null;

  return (
    <section className="space-y-2 rounded-xl border border-border/50 bg-black/40 p-4">
      <div className="flex items-center gap-2">
        <Tag size={14} className="text-primary" />
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-foreground">
          Tags
        </h4>
      </div>
      <ProvenanceTagsInput
        target={{ targetType: "content", targetId: file.sha256 }}
        value={file.tags}
        onChange={(tags) => setTags.mutate(tags)}
        placeholder="Add a tag…"
      />
    </section>
  );
}
