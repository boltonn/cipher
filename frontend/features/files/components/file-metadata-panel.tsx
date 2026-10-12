"use client";

import { formatBytes } from "@/lib/utils";
import { FileText as FileTextIcon, Lock } from "lucide-react";
import type { FileBrowserItem } from "../types";
import { FoundIn } from "./found-in";

/** Path, hashes, filetype, size, and date details for a file -- plus the archive or email it
 * was found in, how it was compressed, and whether it needs a password. Shared between the
 * file viewer dialog's Details tab and the search preview's metadata view. */
export function FileMetadataPanel({ file }: { file: FileBrowserItem }) {
  return (
    <section className="p-4 rounded-xl bg-black/40 border border-border/50 space-y-4">
      <div className="flex items-center gap-2">
        <FileTextIcon size={14} className="text-emerald-500" />
        <h4 className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
          File Metadata
        </h4>
      </div>
      <div className="space-y-3">
        <p className="text-[11px] font-mono text-muted-foreground break-all">
          {file.path ?? file.filename}
        </p>
        {file.parentId && <FoundIn parentId={file.parentId} fileId={file.id} />}
        {file.isEncrypted && (
          <p className="flex items-center gap-1.5 text-[11px] text-foreground">
            <Lock size={12} className="text-muted-foreground" />
            {file.filetypeGroup === "archive"
              ? "Holds encrypted members; any no known password opened are not unpacked"
              : "Encrypted: reading it needs a password"}
          </p>
        )}
        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground font-bold uppercase">SHA256 Hash</p>
          <p className="text-[11px] font-mono text-emerald-500/80 break-all bg-emerald-500/5 p-1.5 rounded border border-emerald-500/10 uppercase">
            {file.sha256}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <DataPoint label="Filetype" value={file.filetypeName ?? file.filetype} />
          <DataPoint label="Type Group" value={file.filetypeGroup} />
          <DataPoint label="Mime Type" value={file.mimeType} />
          <DataPoint label="Storage" value={formatBytes(file.size)} />
          {file.device && <DataPoint label="Device" value={file.device} />}
          {!!file.memberCount && (
            <DataPoint
              label={file.filetypeGroup === "email" ? "Attachments" : "Members"}
              value={file.memberCount.toLocaleString()}
            />
          )}
          {file.compression && (
            <DataPoint
              label="Found compressed"
              value={`${file.compression.encoding}, ${formatBytes(file.compression.size)}`}
            />
          )}
          <DataPoint
            label="Date Created"
            value={file.dateCreated ? new Date(file.dateCreated).toLocaleDateString() : "—"}
          />
          <DataPoint
            label="Last Updated"
            value={
              file.dateLastUpdated ? new Date(file.dateLastUpdated).toLocaleDateString() : "—"
            }
          />
        </div>
      </div>
    </section>
  );
}

const DataPoint = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-0.5 min-w-0">
    <p className="text-muted-foreground uppercase text-[11px] font-semibold tracking-wide leading-none mb-1">
      {label}
    </p>
    <p className="text-foreground font-mono text-[11px] truncate leading-none">{value}</p>
  </div>
);
