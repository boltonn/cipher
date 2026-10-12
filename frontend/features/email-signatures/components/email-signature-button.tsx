"use client";

import { Button } from "@/components/ui/button";
import { EmailSignatureDialog } from "@/features/email-signatures/components/email-signature-dialog";
import { useEmailSignature } from "@/features/email-signatures/hooks/use-email-signatures";
import { PenLine } from "lucide-react";
import { useState } from "react";

/** Opens the email-signature review for an email -- shown only when its signature was read. */
export function EmailSignatureButton({ fileId }: { fileId: string }) {
  const { data: signature } = useEmailSignature(fileId);
  const [isOpen, setOpen] = useState(false);
  if (!signature) return null;
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="h-7 gap-1.5 border-border bg-muted/40 px-2 text-xs"
      >
        <PenLine size={12} /> Email signature
      </Button>
      <EmailSignatureDialog
        fileId={isOpen ? fileId : null}
        onOpenChange={setOpen}
      />
    </>
  );
}
