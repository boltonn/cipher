"use client";

import { DatabaseOverview } from "@/features/database/components/database-overview";

export default function AdminDatabasePage() {
  return (
    <div className="w-full max-w-6xl">
      <p className="mb-4 text-sm text-muted-foreground">
        How much space Postgres uses, by dataset and by table. Click a dataset for its
        own breakdown.
      </p>
      <DatabaseOverview />
    </div>
  );
}
