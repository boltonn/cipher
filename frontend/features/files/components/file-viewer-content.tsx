"use client";

import { CodeBlock } from "@/components/ai-elements/code-block";
import { Button } from "@/components/ui/button";
import { DocxViewerPreview } from "@/components/viewers/docx-viewer";
import { PDFViewer, type PDFViewerHandle } from "@/components/viewers/pdf-viewer";
import { PptxViewerPreview } from "@/components/viewers/pptx-viewer";
import {
  parseDelimitedText,
  TabularViewer,
} from "@/components/viewers/tabular-viewer";
import { XlsxViewerPreview } from "@/components/viewers/xlsx-viewer";
import { useEmail } from "@/features/emails/api";
import { EmailViewer } from "@/features/emails/components/email-viewer";
import { useFileImage } from "@/features/images/api";
import { ImageViewerContent } from "@/features/images/components/image-viewer-content";
import { formatBytes } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { Download, File as FileIcon, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { BundledLanguage } from "shiki";
import { useFileTable } from "../api";
import { getMaxPreviewBytes } from "../file-preview-limits";
import type { FileBrowserItem, FileLocationTarget } from "../types";

/** Backend-extracted (or, for csv/tsv, client-parsed as a fallback) tabular preview. */
export const TABULAR_TYPES = new Set(["csv", "tsv", "json", "jsonl"]);
/** Of `TABULAR_TYPES`, the ones that can also be parsed client-side (via papaparse)
 * before backend extraction has run, so the preview isn't stuck waiting on the pipeline. */
const CLIENT_PARSEABLE_TABULAR_TYPES = new Set(["csv", "tsv"]);
export const CODE_TEXT_GROUPS = new Set(["code", "text"]);

/** Shiki's bundled language ids match most filetyper `filetype` strings directly
 * (python, javascript, json, html, ...); only the mismatches need overriding.
 * An unrecognized id just falls back to unhighlighted text at render time. */
const SHIKI_LANGUAGE_OVERRIDES: Record<string, string> = {
  h: "cpp",
  hpp: "cpp",
  batch: "bat",
  csproj: "xml",
  dockerfile: "docker",
  jsonl: "json",
  ipynb: "json",
  yml: "yaml",
};

function filetypeToShikiLanguage(file: FileBrowserItem): BundledLanguage {
  if (file.filetypeGroup === "text") return "plaintext" as BundledLanguage;
  return (SHIKI_LANGUAGE_OVERRIDES[file.filetype] ?? file.filetype) as BundledLanguage;
}

/**
 * Fetches the extra data `FileViewerContent` needs beyond the file record
 * itself -- raw text for the code/csv viewers, parsed email for `.eml` --
 * shared by `FileViewerDialog` and the search preview pane so each caller
 * doesn't re-derive the same "which fetch does this filetype need" logic.
 */
export function useFileViewerData(file: FileBrowserItem | null, fileUrl?: string) {
  const isTextViewer =
    !!file && (TABULAR_TYPES.has(file.filetype) || CODE_TEXT_GROUPS.has(file.filetypeGroup));
  const { data: textContent, isPending: isTextLoading } = useQuery({
    queryKey: ["file-text", fileUrl],
    queryFn: () => fetch(fileUrl as string).then((res) => res.text()),
    enabled: isTextViewer && !!fileUrl,
  });

  const isEmail = !!file && file.filetype === "eml";
  const { data: email, isPending: isEmailLoading } = useEmail(isEmail ? file?.id : undefined);

  const isTabular = !!file && TABULAR_TYPES.has(file.filetype);
  const {
    data: table,
    isPending: isTableLoading,
    isError: isTableError,
  } = useFileTable(isTabular ? file?.id : undefined);

  return { textContent, isTextLoading, email, isEmailLoading, table, isTableLoading, isTableError };
}

interface FileViewerContentProps {
  file: FileBrowserItem;
  fileUrl?: string;
  textContent?: string;
  isTextLoading: boolean;
  email: import("@/features/emails/types").EmailBase | undefined;
  isEmailLoading: boolean;
  table: import("../types").FileTables | undefined;
  isTableLoading: boolean;
  sidebarFitsInline: boolean;
  /** Query string to highlight in-place; currently only the PDF viewer's text layer supports it. */
  searchQuery?: string;
  /** Where to jump on open -- e.g. a search result's chunk or a chat citation. */
  locationTarget?: FileLocationTarget;
}

export function FileViewerContent({
  file,
  fileUrl,
  textContent,
  isTextLoading,
  email,
  isEmailLoading,
  table,
  isTableLoading,
  sidebarFitsInline,
  searchQuery,
  locationTarget,
}: FileViewerContentProps) {
  // Only files the images pipeline has actually processed have an Image
  // record; most files won't, so this resolves to `undefined` and the plain
  // `<img>` fallback below covers everything else.
  const { data: image } = useFileImage(file.filetypeGroup === "image" ? file.id : undefined);

  if (!fileUrl) return null;

  const maxPreviewBytes = getMaxPreviewBytes(file.filetypeGroup);
  if (file.size > maxPreviewBytes) {
    return <FileTooLarge file={file} fileUrl={fileUrl} maxBytes={maxPreviewBytes} />;
  }

  if (file.filetype === "pdf") {
    return (
      <PdfWithThumbnails
        fileUrl={fileUrl}
        sidebarFitsInline={sidebarFitsInline}
        searchQuery={searchQuery}
        locationTarget={locationTarget}
      />
    );
  }

  if (file.filetype === "docx") {
    return (
      <DocxViewerPreview
        src={fileUrl}
        fileName={file.filename}
        className="h-full"
        showUpload={false}
        initialPage={locationTarget?.pageNumber}
      />
    );
  }

  if (file.filetype === "xlsx") {
    return <XlsxViewerPreview src={fileUrl} fileName={file.filename} className="h-full" />;
  }

  if (file.filetype === "pptx") {
    return (
      <PptxViewerPreview
        src={fileUrl}
        fileName={file.filename}
        className="h-full"
        showUpload={false}
        initialSlide={locationTarget?.pageNumber}
      />
    );
  }

  if (TABULAR_TYPES.has(file.filetype)) {
    if (isTableLoading) return <ViewerLoading label="Loading table..." />;
    if (table && table.sheets.length > 0) {
      return (
        <TabularViewer
          sheets={table.sheets}
          className="h-full"
          downloadUrl={fileUrl}
          downloadFileName={file.filename}
        />
      );
    }
    // Not yet extracted server-side -- csv/tsv can still preview instantly by
    // parsing the raw file client-side; json/jsonl fall through to the plain
    // code view below until extraction catches up.
    if (CLIENT_PARSEABLE_TABULAR_TYPES.has(file.filetype)) {
      if (isTextLoading) return <ViewerLoading label="Loading file..." />;
      if (textContent !== undefined) {
        const parsed = parseDelimitedText(textContent);
        if (parsed.rows.length > 0) {
          return (
            <TabularViewer
              sheets={[{ columns: parsed.columns, rows: parsed.rows }]}
              className="h-full"
            />
          );
        }
      }
    }
  }

  if (CODE_TEXT_GROUPS.has(file.filetypeGroup) || TABULAR_TYPES.has(file.filetype)) {
    if (isTextLoading) return <ViewerLoading label="Loading file..." />;
    if (textContent === undefined) return <ViewerFallback file={file} fileUrl={fileUrl} />;
    return (
      <div className="h-full overflow-auto p-4 bg-background">
        <CodeBlock
          code={textContent}
          language={filetypeToShikiLanguage(file)}
          showLineNumbers={file.filetypeGroup === "code"}
        />
      </div>
    );
  }

  if (file.filetype === "eml") {
    if (isEmailLoading) return <ViewerLoading label="Parsing email..." />;
    if (!email) return <ViewerFallback file={file} fileUrl={fileUrl} />;
    return (
      <EmailViewer
        email={email}
        locationTarget={
          locationTarget?.startOffset !== undefined && locationTarget?.endOffset !== undefined
            ? { startOffset: locationTarget.startOffset, endOffset: locationTarget.endOffset }
            : undefined
        }
      />
    );
  }

  if (file.filetypeGroup === "image") {
    if (image) return <ImageViewerContent image={image} className="h-full" />;
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={fileUrl} alt={file.filename} className="w-full h-full object-contain" />;
  }

  return <ViewerFallback file={file} fileUrl={fileUrl} />;
}

/**
 * `PDFViewer`'s thumbnail sidebar only accepts a mount-time default (no
 * controlled open state), so it can't be toggled after render once we learn
 * the page count from `onDocumentLoadSuccess`. Instead, remount once via a
 * `key` change the first time we learn the doc is multi-page and there's
 * enough width to show the sidebar inline (not as a content-covering overlay,
 * mirroring the same width threshold the component uses internally).
 */
function PdfWithThumbnails({
  fileUrl,
  sidebarFitsInline,
  searchQuery,
  locationTarget,
}: {
  fileUrl: string;
  sidebarFitsInline: boolean;
  searchQuery?: string;
  locationTarget?: FileLocationTarget;
}) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const showThumbnails = numPages !== null && numPages > 1 && sidebarFitsInline;
  const viewerRef = useRef<PDFViewerHandle>(null);
  const { pageNumber, boundingBox } = locationTarget ?? {};

  useEffect(() => {
    if (numPages === null || pageNumber === undefined) return;
    if (boundingBox) {
      viewerRef.current?.scrollToPageArea(pageNumber, {
        top: boundingBox.top * 100,
        left: boundingBox.left * 100,
        width: boundingBox.width * 100,
        height: boundingBox.height * 100,
      });
    } else {
      viewerRef.current?.scrollToPage(pageNumber);
    }
    // Re-run whenever a new location is requested, once the doc has loaded.
  }, [numPages, pageNumber, boundingBox]);

  return (
    <PDFViewer
      ref={viewerRef}
      key={showThumbnails ? "with-sidebar" : "no-sidebar"}
      file={fileUrl}
      className="h-full"
      defaultThumbnailSidebarOpen={showThumbnails}
      onDocumentLoadSuccess={setNumPages}
      searchQuery={searchQuery}
      showUpload={false}
    />
  );
}

export function ViewerLoading({ label }: { label: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-muted-foreground h-full">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <span className="text-[10px] font-black uppercase tracking-[0.3em] text-primary/70">
        {label}
      </span>
    </div>
  );
}

function FileTooLarge({
  file,
  fileUrl,
  maxBytes,
}: {
  file: FileBrowserItem;
  fileUrl: string;
  maxBytes: number;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 text-muted-foreground h-full">
      <TriangleAlert className="h-16 w-16 text-muted-foreground" strokeWidth={1} />
      <div className="text-center space-y-1">
        <p className="text-sm text-foreground max-w-xs truncate">{file.filename}</p>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
          {formatBytes(file.size)} exceeds the {formatBytes(maxBytes)} preview limit
        </p>
      </div>
      <a href={fileUrl} download={file.filename}>
        <Button variant="outline" size="sm" className="gap-2">
          <Download size={14} /> Download
        </Button>
      </a>
    </div>
  );
}

export function ViewerFallback({ file, fileUrl }: { file: FileBrowserItem; fileUrl: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 text-muted-foreground h-full">
      <FileIcon className="h-16 w-16 text-muted-foreground" strokeWidth={1} />
      <div className="text-center space-y-1">
        <p className="text-sm text-foreground max-w-xs truncate">{file.filename}</p>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
          No preview available for {file.filetype || "this file type"}
        </p>
      </div>
      <a href={fileUrl} download={file.filename}>
        <Button variant="outline" size="sm" className="gap-2">
          <Download size={14} /> Download
        </Button>
      </a>
    </div>
  );
}
