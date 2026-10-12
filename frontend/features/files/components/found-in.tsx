"use client";

import { Button } from "@/components/ui/button";
import { useEmail } from "@/features/emails/api";
import { useEmailAttachments } from "@/features/emails/hooks/use-email-attachments";
import { ChevronLeft, ChevronRight, CornerLeftUp } from "lucide-react";
import Link from "next/link";
import { useFile, useFileChildren } from "../api";
import type { FileRecord } from "../types";

/** The archive or email a file was found in, linked, with previous / next through the files found beside it. */
export function FoundIn({
  parentId,
  fileId,
}: {
  parentId: string;
  fileId?: string;
}) {
  const { data: parent } = useFile(parentId);
  return (
    <div className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted-foreground">
      <CornerLeftUp size={12} className="shrink-0" />
      Found in
      <Link
        href={`/files/${parentId}`}
        title={parent?.path}
        className="truncate text-foreground hover:underline"
      >
        {parent?.filename ?? "its parent file"}
      </Link>
      {fileId &&
        parent &&
        (parent.filetypeGroup === "email" ? (
          <AttachmentSiblingNav emailId={parentId} fileId={fileId} />
        ) : (
          <MemberSiblingNav parentId={parentId} fileId={fileId} />
        ))}
    </div>
  );
}

/** Previous / next attachment of the same email (images its body shows are not attachments). */
function AttachmentSiblingNav({
  emailId,
  fileId,
}: {
  emailId: string;
  fileId: string;
}) {
  const { data: email } = useEmail(emailId);
  return (
    <SiblingFileNav
      siblings={useEmailAttachments(emailId, email)}
      fileId={fileId}
    />
  );
}

/** Previous / next file found in the same archive. */
function MemberSiblingNav({
  parentId,
  fileId,
}: {
  parentId: string;
  fileId: string;
}) {
  const { data: siblings = [] } = useFileChildren(parentId);
  return <SiblingFileNav siblings={siblings} fileId={fileId} />;
}

function SiblingFileNav({
  siblings,
  fileId,
}: {
  siblings: FileRecord[];
  fileId: string;
}) {
  const index = siblings.findIndex((sibling) => sibling.id === fileId);
  if (index < 0 || siblings.length < 2) return null;
  return (
    <div className="ml-auto flex shrink-0 items-center">
      <SiblingLink
        sibling={siblings[index - 1]}
        label="Previous file found with it"
      >
        <ChevronLeft size={13} />
      </SiblingLink>
      <span className="px-0.5 tabular-nums">
        {index + 1} of {siblings.length}
      </span>
      <SiblingLink
        sibling={siblings[index + 1]}
        label="Next file found with it"
      >
        <ChevronRight size={13} />
      </SiblingLink>
    </div>
  );
}

function SiblingLink({
  sibling,
  label,
  children,
}: {
  sibling?: FileRecord;
  label: string;
  children: React.ReactNode;
}) {
  if (!sibling) {
    return (
      <Button
        variant="ghost"
        size="icon"
        className="size-6"
        disabled
        aria-label={label}
      >
        {children}
      </Button>
    );
  }
  return (
    <Button asChild variant="ghost" size="icon" className="size-6">
      <Link
        href={`/files/${sibling.id}`}
        aria-label={label}
        title={sibling.filename}
      >
        {children}
      </Link>
    </Button>
  );
}
