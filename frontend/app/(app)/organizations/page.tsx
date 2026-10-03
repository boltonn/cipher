"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { useEntityList } from "@/features/entities/hooks/use-entities";
import { UnplacedOrganizations } from "@/features/organizations/components/unplaced-organizations";
import type { EntitySearchParameters } from "@/features/entities/types";
import { BadgeCheck, Building2, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const LIMIT = 48;

export default function OrganizationsPage() {
  const [params, setParams] = useState<EntitySearchParameters>({
    entityType: "organization",
    sortBy: "mention_count",
    sortOrder: "desc",
    limit: LIMIT,
    page: 1,
  });
  const { data, isPending, isFetching, isError, refetch } =
    useEntityList(params);
  const organizations = data?.data ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="mx-auto max-w-400 px-6 pb-20 pt-5">
      <PageHeader
        eyebrow="Organizations"
        value={`${total.toLocaleString()} ${total === 1 ? "organization" : "organizations"}`}
      />

      <div className="mt-4">
        <SearchBarShell
          isActive={isFetching}
          icon={<Search size={18} strokeWidth={1.5} />}
        >
          <SearchInput
            ariaLabel="Search organizations"
            placeholder="Search by name..."
            value={params.query ?? ""}
            onSearch={(query) =>
              setParams((prev) => ({
                ...prev,
                query: query || undefined,
                page: 1,
              }))
            }
          />
        </SearchBarShell>
      </div>

      <div className="mt-4">
        <UnplacedOrganizations />
      </div>

      <main className="mt-6">
        {isError ? (
          <PageError
            title="Couldn’t load organizations"
            body="The request failed. This is usually temporary — try again."
            onRetry={() => refetch()}
          />
        ) : isPending ? (
          <PageLoading
            icon={Building2}
            label="Loading organizations…"
            onRetry={() => refetch()}
          />
        ) : organizations.length === 0 ? (
          <EmptyState
            icon={Building2}
            title="No organizations found"
            body={
              params.query
                ? "No organizations match this search."
                : "Extract entities or create one manually."
            }
          />
        ) : (
          <div className="space-y-8">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {organizations.map((org) => (
                <Link
                  key={org.id}
                  href={`/organizations/${org.id}`}
                  className="group rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-primary/50"
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium text-foreground group-hover:text-primary">
                    <Building2
                      size={14}
                      className="shrink-0 text-muted-foreground"
                    />
                    <span className="truncate">{org.displayName}</span>
                    {org.isVerified && (
                      <BadgeCheck size={13} className="shrink-0 text-primary" />
                    )}
                  </span>
                  <span className="mt-1 block text-xs tabular-nums text-muted-foreground">
                    {org.mentionCount.toLocaleString()} mentions ·{" "}
                    {org.relationshipCount.toLocaleString()} relationships
                  </span>
                </Link>
              ))}
            </div>
            <Pagination
              currentPage={params.page}
              totalItems={total}
              itemsPerPage={LIMIT}
              onPageChange={(page) => setParams((prev) => ({ ...prev, page }))}
              isLoading={isFetching}
            />
          </div>
        )}
      </main>
    </div>
  );
}
