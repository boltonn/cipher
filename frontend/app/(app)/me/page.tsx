"use client";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { MyDatasets } from "@/features/me/components/my-datasets";
import { SearchList } from "@/features/me/components/search-lists";
import { TagStatsTable } from "@/features/me/components/tag-stats-table";
import { useMe } from "@/features/users/hooks/use-me";
import { Settings, UserRound } from "lucide-react";
import Link from "next/link";

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={className}>
      <h2 className="mb-2 text-xs font-medium text-muted-foreground">{title}</h2>
      {children}
    </section>
  );
}

/** Your corner of the app: searches you keep coming back to, your datasets, and the tags you label. */
export default function MyWorkspacePage() {
  const { data: me } = useMe();

  return (
    <div className="mx-auto flex w-full max-w-400 flex-col gap-6 px-6 pb-10 pt-5">
      <PageHeader
        eyebrow="My workspace"
        icon={<UserRound size={13} className="text-primary/70" />}
        value={me ? `${me.name}${me.isAdmin ? " · admin" : ""}` : undefined}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/settings">
              <Settings className="size-3.5" />
              Settings
            </Link>
          </Button>
        }
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Section title="Saved searches">
          <SearchList saved limit={50} />
        </Section>
        <Section title="Recent searches">
          <SearchList saved={false} limit={15} />
        </Section>
        <Section title="Your datasets">
          <MyDatasets />
        </Section>
      </div>
      <Section title="Tags">
        <TagStatsTable />
      </Section>
    </div>
  );
}
