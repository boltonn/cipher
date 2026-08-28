"use client";

import type { DataTableFilters, DataTableSortOrder } from "@/components/data-table/types";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useDatasetsList } from "@/features/datasets/api";
import { DatasetRequestForm } from "@/features/datasets/components/dataset-create-form";
import {
  DatasetsContainer,
  type DatasetsViewMode,
} from "@/features/datasets/components/datasets-container";
import { DatasetsSearchBar } from "@/features/datasets/components/datasets-search-bar";
import type { DatasetRequest } from "@/features/datasets/types";
import { cn } from "@/lib/utils";
import { Database, LayoutGrid, Plus, Table2 } from "lucide-react";
import { useState } from "react";

/** Maps the DataTable's generic per-column filters onto the backend's DatasetRequest shape. */
function toDatasetRequest(filters: DataTableFilters): Partial<DatasetRequest> {
  const name = filters.name as string | undefined;
  const dateCreated = filters.dateCreated as { from?: string; to?: string } | undefined;
  const dateLastUpdated = filters.dateLastUpdated as { from?: string; to?: string } | undefined;

  return {
    query: name || undefined,
    dateCreatedFrom: dateCreated?.from,
    dateCreatedTo: dateCreated?.to,
    dateLastUpdatedFrom: dateLastUpdated?.from,
    dateLastUpdatedTo: dateLastUpdated?.to,
  };
}

export default function DatasetSearchPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [viewMode, setViewMode] = useState<DatasetsViewMode>("card");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [sortBy, setSortBy] = useState<string>("name");
  const [sortOrder, setSortOrder] = useState<DataTableSortOrder>("asc");
  const [filters, setFilters] = useState<DataTableFilters>({});

  const { data, isLoading, isFetching } = useDatasetsList({
    ...toDatasetRequest(filters),
    sortBy: sortBy as DatasetRequest["sortBy"],
    sortOrder,
    limit,
    page,
  });

  const datasets = data?.data ?? [];
  const total = data?.total ?? 0;

  const handleSortChange = (field: string, order: DataTableSortOrder) => {
    setSortBy(field);
    setSortOrder(order);
    setPage(1);
  };

  const handleFilterChange = (key: string, value: DataTableFilters[string]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const handleSearch = (query: string) => {
    handleFilterChange("name", query || undefined);
  };

  const clearAllFilters = () => {
    setFilters({});
    setPage(1);
  };

  return (
    <div className="max-w-350 mx-auto px-6 relative pb-20">
      <PageHeader
        eyebrow="Registry"
        icon={<Database size={10} className="text-primary/50" />}
        value={`${total.toLocaleString()} ${total === 1 ? "Dataset" : "Datasets"}`}
        actions={
          <>
            <div className="flex items-center p-1 rounded-lg bg-muted/50 border border-border/50 gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setViewMode("card")}
                aria-label="Card view"
                className={cn(
                  "h-7 w-7",
                  viewMode === "card" ? "text-primary bg-primary/10" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <LayoutGrid size={14} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setViewMode("table")}
                aria-label="Table view"
                className={cn(
                  "h-7 w-7",
                  viewMode === "table" ? "text-primary bg-primary/10" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Table2 size={14} />
              </Button>
            </div>

            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 bg-muted/40 border-border text-muted-foreground hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
                >
                  <Plus size={14} className="mr-1.5" />
                  Request Dataset
                </Button>
              </DialogTrigger>
              <DialogContent className="p-0 border-border bg-transparent w-fit ring-0">
                <DialogTitle className="sr-only">Request Dataset</DialogTitle>
                <DatasetRequestForm onClose={() => setCreateOpen(false)} />
              </DialogContent>
            </Dialog>
          </>
        }
      />

      {/* 2. Search bar */}
      <div className="mt-4">
        <DatasetsSearchBar
          query={filters.name as string | undefined}
          onSearch={handleSearch}
          onClearFilters={clearAllFilters}
          isSearching={isFetching}
        />
      </div>

      {/* 3. Content Area */}
      <div className="mt-4 relative z-10">
        <DatasetsContainer
          viewMode={viewMode}
          datasets={datasets}
          total={total}
          page={page}
          limit={limit}
          isLoading={isLoading}
          sortBy={sortBy}
          sortOrder={sortOrder}
          filters={filters}
          onPageChange={setPage}
          onLimitChange={(newLimit) => {
            setLimit(newLimit);
            setPage(1);
          }}
          onSortChange={handleSortChange}
          onFilterChange={handleFilterChange}
        />
      </div>
    </div>
  );
}
