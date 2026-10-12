"use client";

import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CommentSection } from "@/features/comments/components/comment-section";
import { EntityMentionText } from "@/features/entities/components/entity-mention-text";
import { cn } from "@/lib/utils";
import {
  HardDrive,
  Loader2,
  MessageSquare,
  ScanText,
  ScrollText,
  Waypoints,
} from "lucide-react";
import { useState } from "react";
import { useFile, useFileText } from "../api";
import type { FileBrowserItem } from "../types";
import { FileMetadataPanel } from "./file-metadata-panel";
import { FileSummary } from "./file-summary";
import { FileTagsEditor } from "./file-tags-editor";

/** A file's Details (summary, metadata, where it was found, tags), extracted Text and Comments --
 * the right-hand panel of the file viewer dialog and the file page. */
export function FileSidePanel({
  file,
  showText = true,
  imageDetails,
  className,
}: {
  file: FileBrowserItem;
  /** The image analysis (similar images, faces, camera) when the file is an analysed image. */
  imageDetails?: React.ReactNode;
  /** Off where the page already shows the text beside it. */
  showText?: boolean;
  className?: string;
}) {
  return (
    <Tabs defaultValue="details" className={cn("w-full", className)}>
      <TabsList className="w-full bg-muted/50 border border-border/50 h-10 p-1">
        <TabsTrigger
          value="details"
          className="flex-1 text-xs font-medium data-[state=active]:bg-primary"
        >
          <HardDrive size={12} className="mr-2" /> Details
        </TabsTrigger>
        {showText && (
          <TabsTrigger
            value="text"
            className="flex-1 text-xs font-medium data-[state=active]:bg-primary"
            disabled={!file.id}
          >
            <ScrollText size={12} className="mr-2" /> Text
          </TabsTrigger>
        )}
        <TabsTrigger
          value="comments"
          className="flex-1 text-xs font-medium data-[state=active]:bg-primary"
          disabled={!file.id}
        >
          <MessageSquare size={12} className="mr-2" /> Comments
        </TabsTrigger>
      </TabsList>

      <TabsContent value="details" className="mt-4">
        <div className="space-y-4">
          {file.id && <FileSummary fileId={file.id} />}
          {imageDetails}
          <FileMetadataPanel file={file} />
          {file.id && <FileTagsEditor fileId={file.id} />}
        </div>
      </TabsContent>

      {showText && (
        <TabsContent value="text" className="mt-4">
          <FileTextTab fileId={file.id} />
        </TabsContent>
      )}

      <TabsContent value="comments" className="mt-4">
        {file.id ? (
          <CommentSection commentableType="file" commentableId={file.id} />
        ) : (
          <p className="text-[11px] text-muted-foreground text-center italic py-4">
            Comments unavailable.
          </p>
        )}
      </TabsContent>
    </Tabs>
  );
}

function FileTextTab({ fileId }: { fileId?: string }) {
  const { data, isPending, isError } = useFileText(fileId);
  const { data: file } = useFile(fileId);
  const [showEntities, setShowEntities] = useState(false);

  if (!fileId) {
    return (
      <p className="text-[11px] text-muted-foreground text-center italic py-4">
        Text unavailable.
      </p>
    );
  }
  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" /> Loading extracted text...
      </div>
    );
  }
  if (isError || !data) {
    return (
      <p className="text-[11px] text-muted-foreground text-center italic py-4">
        Not extracted yet.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {data.imagePages.length > 0 && (
        <p className="flex items-center gap-1.5 text-[11px] text-annotation">
          <ScanText size={12} />
          {data.imagePages.length} image-based page
          {data.imagePages.length === 1 ? "" : "s"} (
          {data.imagePages.join(", ")}) ·{" "}
          {data.ocrModel ? `text by OCR (${data.ocrModel})` : "no OCR text yet"}
        </p>
      )}
      {file?.datasetId && (
        <label className="flex items-center justify-end gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
          <Waypoints size={12} /> Entities
          <Switch checked={showEntities} onCheckedChange={setShowEntities} />
        </label>
      )}
      {showEntities && file?.datasetId ? (
        <div className="max-h-125 overflow-auto rounded-lg border border-border/50 bg-black/40 text-[11px]">
          <EntityMentionText fileId={fileId} datasetId={file.datasetId} />
        </div>
      ) : (
        <pre className="text-[11px] font-mono text-foreground leading-relaxed whitespace-pre-wrap break-words p-3 rounded-lg bg-black/40 border border-border/50 max-h-125 overflow-auto">
          {data.text}
        </pre>
      )}
    </div>
  );
}
