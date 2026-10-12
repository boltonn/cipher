"use client";

import { EmptyState } from "@/components/empty-state";
import { PageError } from "@/components/page-loading";
import { Pagination } from "@/components/pagination";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmailSignatureDialog } from "@/features/email-signatures/components/email-signature-dialog";
import { useEmailSignatures } from "@/features/email-signatures/hooks/use-email-signatures";
import type { EmailSignatureSearchParameters } from "@/features/email-signatures/types";
import { cn } from "@/lib/utils";
import { ChevronRight, FileSearch, PenLine, Search } from "lucide-react";
import { useState } from "react";

const STATUSES: { value: boolean | undefined; label: string }[] = [
  { value: true, label: "To review" },
  { value: false, label: "Reviewed" },
  { value: undefined, label: "All" },
];

/**
 * Emails whose sender's email signature was read: who signed, the organization chain,
 * and how many proposed relationships are left. Each opens the email-signature workspace.
 */
export function EmailSignaturesQueue({ datasetIds }: { datasetIds: string[] }) {
  const [params, setParams] = useState<
    Omit<EmailSignatureSearchParameters, "datasetIds">
  >({
    isPending: true,
    page: 1,
    limit: 25,
  });
  const { data, isPending, isFetching, isError, refetch } = useEmailSignatures({
    ...params,
    datasetIds,
  });
  const rows = data?.data ?? [];
  // by file id, not row index: reviewing an email drops it from "To review" and the rows shift
  const [openFileId, setOpenFileId] = useState<string | null>(null);
  const openIndex = rows.findIndex((r) => r.fileId === openFileId);
  const update = (patch: Partial<typeof params>) =>
    setParams((prev) => ({ ...prev, page: 1, ...patch }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <ButtonGroup>
          {STATUSES.map(({ value, label }) => (
            <Button
              key={label}
              variant="outline"
              size="sm"
              aria-pressed={params.isPending === value}
              onClick={() => update({ isPending: value })}
              className={cn(
                "h-10 border-border text-xs",
                params.isPending === value
                  ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                  : "bg-muted/40 text-muted-foreground hover:text-foreground"
              )}
            >
              {label}
            </Button>
          ))}
        </ButtonGroup>
        <div className="min-w-0 flex-1">
          <SearchBarShell
            isActive={isFetching}
            icon={<Search size={18} strokeWidth={1.5} />}
          >
            <SearchInput
              ariaLabel="Search email signatures"
              placeholder="Search by signer, organization, sender or subject..."
              value={params.query ?? ""}
              onSearch={(query) => update({ query: query || undefined })}
            />
          </SearchBarShell>
        </div>
      </div>

      {isError ? (
        <PageError
          title="Couldn’t load email signatures"
          body="The request failed. This is usually temporary — try again."
          onRetry={() => refetch()}
        />
      ) : !isPending && rows.length === 0 ? (
        <EmptyState
          icon={PenLine}
          title={
            params.isPending ? "Nothing left to review" : "No email signatures"
          }
          body={
            params.query
              ? "No email signature matches this search."
              : "Email signatures appear here once `extract-signatures` has read the datasets’ emails."
          }
        />
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Signed by</TableHead>
                  <TableHead>Organization</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead className="w-28">Sent</TableHead>
                  <TableHead className="w-28 text-right">
                    Relationships
                  </TableHead>
                  <TableHead className="w-24" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.fileId}
                    className="cursor-pointer"
                    onClick={() => setOpenFileId(row.fileId)}
                  >
                    <TableCell className="font-medium text-foreground">
                      {row.personName ?? "—"}
                    </TableCell>
                    <TableCell>
                      <span className="flex flex-wrap items-center gap-1 text-xs">
                        {row.organizations.map((name, i) => (
                          <span
                            key={`${name}-${i}`}
                            className="inline-flex items-center gap-1"
                          >
                            {i > 0 && (
                              <ChevronRight
                                size={11}
                                className="text-muted-foreground"
                              />
                            )}
                            <span
                              className={
                                i === 0
                                  ? "text-foreground"
                                  : "text-muted-foreground"
                              }
                            >
                              {name}
                            </span>
                          </span>
                        ))}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-80">
                      <div className="truncate text-xs text-foreground">
                        {row.subject ?? "(no subject)"}
                      </div>
                      <div className="truncate text-[11px] text-muted-foreground">
                        {row.sender}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs tabular-nums text-muted-foreground">
                      {row.dateSent
                        ? new Date(row.dateSent).toLocaleDateString()
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums">
                      {row.pendingCount > 0 ? (
                        <span className="text-annotation">
                          {row.pendingCount} to review
                        </span>
                      ) : (
                        <span className="text-muted-foreground">
                          {row.relationshipCount} reviewed
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 gap-1 px-2 text-xs"
                      >
                        <FileSearch size={12} /> Review
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <Pagination
            currentPage={params.page}
            totalItems={data?.total ?? 0}
            itemsPerPage={params.limit}
            onPageChange={(page) => setParams((prev) => ({ ...prev, page }))}
            isLoading={isFetching}
          />
        </>
      )}

      <EmailSignatureDialog
        fileId={openFileId}
        onOpenChange={(open) => !open && setOpenFileId(null)}
        onPrevious={
          openIndex > 0
            ? () => setOpenFileId(rows[openIndex - 1].fileId)
            : undefined
        }
        onNext={
          openIndex >= 0 && openIndex < rows.length - 1
            ? () => setOpenFileId(rows[openIndex + 1].fileId)
            : undefined
        }
      />
    </div>
  );
}
