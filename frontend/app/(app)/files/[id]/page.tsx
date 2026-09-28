"use client";

import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Button } from "@/components/ui/button";
import { EntityMentionText } from "@/features/entities/components/entity-mention-text";
import { useFile } from "@/features/files/api";
import { ArrowLeft, FileText, Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { use } from "react";

/**
 * Full-page annotated extracted text for one file -- the displacy-style entity
 * view (`EntityMentionText`) given the whole viewport instead of a preview
 * pane. Reached from a search result or an entity's "Find in text": the
 * `?focus=<char offset>` param scrolls the matching mention into view on load,
 * `?from=` is an optional back link.
 */
export default function FilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const search = useSearchParams();
  const focusParam = search.get("focus");
  const focusOffset = focusParam != null && focusParam !== "" ? Number(focusParam) : undefined;
  const backHref = search.get("from") ?? undefined;

  const { data: file, isPending, isError, refetch } = useFile(id);

  if (isPending) {
    return <PageLoading icon={FileText} label="Loading file…" onRetry={() => refetch()} />;
  }

  if (isError || !file) {
    return (
      <PageError
        className="mt-24"
        title="Couldn’t load this file"
        body="Its record didn’t come back. This is usually temporary — try again, or head back."
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-5xl flex-col px-6 pb-6 pt-5">
      <PageHeader
        eyebrow="File"
        icon={<FileText size={10} className="text-primary/50" />}
        value={file.filename}
        actions={
          backHref ? (
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-2 text-xs"
              onClick={() => {
                // Prefer real back nav -- it restores the caller's scroll and
                // in-memory state (tab, month, filters). Fall back to the
                // `from` href only when there is no history (deep link / new tab).
                if (typeof window !== "undefined" && window.history.length > 1) router.back();
                else router.push(backHref);
              }}
            >
              <ArrowLeft size={13} /> Back
            </Button>
          ) : undefined
        }
      />

      <div className="mt-4 min-h-0 flex-1 overflow-hidden rounded-xl border border-border bg-muted/40 shadow-xl">
        {file.datasetId ? (
          <EntityMentionText
            fileId={id}
            datasetId={file.datasetId}
            focusOffset={Number.isFinite(focusOffset) ? focusOffset : undefined}
            className="h-full overflow-auto"
          />
        ) : (
          <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Resolving dataset…
          </div>
        )}
      </div>
    </div>
  );
}
