"use client";

import { useDatasets } from "@/features/datasets/api";
import { Database, Lock } from "lucide-react";
import Link from "next/link";

/** Datasets you can open, then ones that are only discoverable (request access from the Datasets page). */
export function MyDatasets() {
  const { data, isPending } = useDatasets({ limit: 100 });
  if (isPending) return <p className="px-2 text-sm text-muted-foreground">Loading…</p>;
  const datasets = (data?.pages.flatMap((page) => page.data) ?? []).toSorted(
    (a, b) => Number(b.hasAccess) - Number(a.hasAccess)
  );
  if (!datasets.length) return <p className="px-2 text-sm text-muted-foreground">No datasets yet.</p>;

  return (
    <ul className="space-y-0.5">
      {datasets.map((dataset) => (
        <li key={dataset.id}>
          <Link
            href={dataset.hasAccess ? `/datasets/${dataset.id}` : "/datasets"}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
          >
            {dataset.hasAccess ? (
              <Database className="size-3.5 text-primary" />
            ) : (
              <Lock className="size-3.5 text-muted-foreground" />
            )}
            <span className={dataset.hasAccess ? "truncate text-foreground" : "truncate text-muted-foreground"}>
              {dataset.name}
            </span>
            {!dataset.hasAccess && <span className="ml-auto text-xs text-muted-foreground">No access</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}
