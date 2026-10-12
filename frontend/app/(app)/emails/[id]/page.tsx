"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { useEmail } from "@/features/emails/api";
import { EmailViewer } from "@/features/emails/components/email-viewer";
import { Mail, MailX } from "lucide-react";
import { use } from "react";

export default function EmailDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: email, isPending, error } = useEmail(id);

  if (isPending) {
    return <PageLoading icon={Mail} label="Loading email…" />;
  }

  if (error || !email) {
    return (
      <div className="mx-auto max-w-400 px-6">
        <EmptyState
          className="mt-24"
          icon={MailX}
          title="Couldn’t load this email"
          body="It may have been removed, or the request failed. Try again from the email list."
        />
      </div>
    );
  }

  return (
    <div className="max-w-400 mx-auto px-6 pb-6 pt-5 h-full flex flex-col">
      <PageHeader eyebrow="Email" value={email.metadata.title ?? "(no subject)"} />
      <div className="flex-1 min-h-0 rounded-2xl overflow-hidden border border-border">
        <EmailViewer email={email} fileId={id} />
      </div>
    </div>
  );
}
