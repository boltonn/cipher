"use client";

import { PageHeader } from "@/components/page-header";
import { useEmail } from "@/features/emails/api";
import { EmailViewer } from "@/features/emails/components/email-viewer";
import { Loader2 } from "lucide-react";
import { use } from "react";

export default function EmailDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: email, isPending, error } = useEmail(id);

  if (isPending) {
    return (
      <div className="flex items-center justify-center py-48 text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin text-primary/40" />
      </div>
    );
  }

  if (error || !email) {
    return (
      <div className="flex items-center justify-center py-48 text-muted-foreground text-sm">
        Failed to load email.
      </div>
    );
  }

  return (
    <div className="max-w-400 mx-auto px-6 pb-20 h-screen flex flex-col">
      <PageHeader eyebrow="Email" value={email.metadata.title ?? "(no subject)"} />
      <div className="mt-4 flex-1 min-h-0 rounded-2xl overflow-hidden border border-border">
        <EmailViewer email={email} />
      </div>
    </div>
  );
}
