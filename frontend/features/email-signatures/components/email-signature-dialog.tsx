"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmailSignatureWorkspace } from "@/features/email-signatures/components/email-signature-workspace";
import { useEmailSignature } from "@/features/email-signatures/hooks/use-email-signatures";
import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import Link from "next/link";

/** The email-signature workspace for one email, with previous / next through the queue. */
export function EmailSignatureDialog({
  fileId,
  onOpenChange,
  onPrevious,
  onNext,
}: {
  fileId: string | null;
  onOpenChange: (open: boolean) => void;
  onPrevious?: () => void;
  onNext?: () => void;
}) {
  const { data: signature } = useEmailSignature(fileId ?? undefined);
  return (
    <Dialog open={!!fileId} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100vh-3rem)] flex-col gap-3 border-border bg-card sm:max-w-[min(96rem,calc(100vw-3rem))]">
        <DialogHeader className="shrink-0 flex-row items-start gap-3 space-y-0 pr-8">
          <div className="min-w-0 flex-1">
            <DialogTitle className="truncate">
              {signature?.subject ?? "Email signature"}
            </DialogTitle>
            <DialogDescription className="truncate text-xs">
              {[
                signature?.sender,
                signature?.dateSent &&
                  new Date(signature.dateSent).toLocaleDateString(),
              ]
                .filter(Boolean)
                .join(" · ")}
            </DialogDescription>
          </div>
          <span className="flex shrink-0 items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              disabled={!onPrevious}
              onClick={onPrevious}
              aria-label="Previous email"
              className="h-8 w-8"
            >
              <ChevronLeft size={14} />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              disabled={!onNext}
              onClick={onNext}
              aria-label="Next email"
              className="h-8 w-8"
            >
              <ChevronRight size={14} />
            </Button>
            {fileId && (
              <Button
                asChild
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs"
              >
                <Link href={`/files/${fileId}`}>
                  Open email <ExternalLink size={12} />
                </Link>
              </Button>
            )}
          </span>
        </DialogHeader>
        {fileId && <EmailSignatureWorkspace key={fileId} fileId={fileId} />}
      </DialogContent>
    </Dialog>
  );
}
