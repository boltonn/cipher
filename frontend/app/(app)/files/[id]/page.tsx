"use client";

import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  useElementWidth,
  useInlineThumbnailSidebar,
} from "@/components/viewers/document-viewer-sidebar";
import { EntityMentionText } from "@/features/entities/components/entity-mention-text";
import { filesService, useFile, useFileText } from "@/features/files/api";
import { FileSidePanel } from "@/features/files/components/file-side-panel";
import { FileTextCorrection } from "@/features/files/components/file-text-correction";
import { useIsAdmin } from "@/features/users/hooks/use-me";
import {
  FileViewerContent,
  useFileViewerData,
} from "@/features/files/components/file-viewer-content";
import type { FileBrowserItem } from "@/features/files/types";
import type { OverlayBox } from "@/features/faces/components/face-image-overlay";
import {
  FileImageDetails,
  useFileImageDetails,
} from "@/features/images/components/image-details";
import { cn } from "@/lib/utils";
import { ArrowLeft, FileText, Loader2, PencilLine, Table2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useState } from "react";

const MODES = [
  { value: "view", label: "View" },
  { value: "text", label: "Text" },
] as const;

/**
 * A file's page: the file itself (View) or its extracted text with entity mentions
 * (Text), beside the same Details / Comments panel as the file viewer dialog.
 * `?focus=<char offset>` (a search result, an entity's "Find in text") opens Text
 * scrolled to that mention; `?from=` is an optional back link.
 */
export default function FilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const search = useSearchParams();
  const focusParam = search.get("focus");
  const focusOffset =
    focusParam != null && focusParam !== "" ? Number(focusParam) : undefined;
  const backHref = search.get("from") ?? undefined;

  const { data: file, isPending, isError, refetch } = useFile(id);
  const { image, selection } = useFileImageDetails({
    id,
    filetypeGroup: file?.filetypeGroup ?? "",
  });
  const { data: fileText } = useFileText(id);
  const [isCorrecting, setCorrecting] = useState(false);
  const isAdmin = useIsAdmin();
  const canCorrect = isAdmin && (fileText?.ocrPages.length ?? 0) > 0;
  const [mode, setMode] = useState<"view" | "text">(
    focusParam ? "text" : "view"
  );
  const [lastFocusParam, setLastFocusParam] = useState(focusParam);
  if (focusParam !== lastFocusParam) {
    setLastFocusParam(focusParam);
    if (focusParam) setMode("text");
  }

  if (isPending) {
    return (
      <PageLoading
        icon={FileText}
        label="Loading file…"
        onRetry={() => refetch()}
      />
    );
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
    <div className="mx-auto flex h-full w-full max-w-400 flex-col px-4 pb-6 pt-5 md:px-6">
      <PageHeader
        eyebrow="File"
        icon={<FileText size={10} className="text-primary/50" />}
        value={file.filename}
        actions={
          <div className="flex items-center gap-2">
            {file.filetypeGroup === "table" && (
              <Button
                asChild
                variant="outline"
                size="sm"
                className="h-8 gap-2 text-xs"
              >
                <Link href={`/tables/${file.sha256}`}>
                  <Table2 size={13} /> Table view
                </Link>
              </Button>
            )}
            {backHref && (
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-2 text-xs"
                onClick={() => {
                  // Prefer real back nav -- it restores the caller's scroll and
                  // in-memory state (tab, month, filters). Fall back to the
                  // `from` href only when there is no history (deep link / new tab).
                  if (
                    typeof window !== "undefined" &&
                    window.history.length > 1
                  )
                    router.back();
                  else router.push(backHref);
                }}
              >
                <ArrowLeft size={13} /> Back
              </Button>
            )}
          </div>
        }
      />

      <div className="mt-4 flex min-h-0 flex-1 flex-col overflow-y-auto rounded-xl border border-border bg-card shadow-xl md:flex-row md:overflow-hidden">
        <section className="flex min-h-[70vh] min-w-0 flex-1 flex-col md:min-h-0">
          <div className="flex shrink-0 items-center border-b border-border bg-muted/30 px-3 py-2">
            <ButtonGroup>
              {MODES.map((option) => (
                <Button
                  key={option.value}
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-pressed={mode === option.value}
                  onClick={() => setMode(option.value)}
                  className={cn(
                    "h-7 border-border px-3 text-xs",
                    mode === option.value
                      ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                      : "bg-muted/40 text-muted-foreground hover:text-foreground"
                  )}
                >
                  {option.label}
                </Button>
              ))}
            </ButtonGroup>
            {mode === "text" && fileText?.isContentCorrected && (
              <span
                className="ml-3 text-[11px] text-muted-foreground"
                title="An analyst corrected this OCR text; pipeline re-runs keep it"
              >
                Corrected text
              </span>
            )}
            {mode === "text" && canCorrect && !isCorrecting && (
              <Button
                variant="outline"
                size="sm"
                className="ml-auto h-7 gap-1.5 text-xs"
                onClick={() => setCorrecting(true)}
              >
                <PencilLine size={12} /> Correct text
              </Button>
            )}
          </div>
          <div className="min-h-0 flex-1 bg-muted/40">
            {mode === "view" ? (
              <FileView
                file={{ ...file, type: "file" }}
                imageOverlayBoxes={selection.overlayBoxes}
              />
            ) : isCorrecting && fileText ? (
              <FileTextCorrection
                fileId={id}
                text={fileText.text}
                onDone={() => setCorrecting(false)}
              />
            ) : file.datasetId ? (
              <EntityMentionText
                fileId={id}
                datasetId={file.datasetId}
                focusOffset={
                  Number.isFinite(focusOffset) ? focusOffset : undefined
                }
                className="h-full overflow-auto"
              />
            ) : (
              <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Resolving dataset…
              </div>
            )}
          </div>
        </section>
        <aside className="w-full shrink-0 border-t border-border bg-popover p-4 md:w-100 md:overflow-y-auto md:border-l md:border-t-0">
          <FileSidePanel
            file={{ ...file, type: "file" }}
            showText={false}
            imageDetails={
              image && <FileImageDetails image={image} selection={selection} />
            }
          />
        </aside>
      </div>
    </div>
  );
}

/** The file as its own viewer shows it: image, PDF, email with its attachments, and so on. */
function FileView({
  file,
  imageOverlayBoxes,
}: {
  file: FileBrowserItem;
  imageOverlayBoxes?: OverlayBox[];
}) {
  const fileUrl = filesService.getFileUrl(file.id as string);
  const viewerData = useFileViewerData(file, fileUrl);
  const [viewerRef, viewerWidth] = useElementWidth<HTMLDivElement>();
  const sidebarFitsInline = useInlineThumbnailSidebar(viewerWidth);
  return (
    <div ref={viewerRef} className="h-full">
      <FileViewerContent
        file={file}
        fileUrl={fileUrl}
        sidebarFitsInline={sidebarFitsInline}
        imageOverlayBoxes={imageOverlayBoxes}
        {...viewerData}
      />
    </div>
  );
}
