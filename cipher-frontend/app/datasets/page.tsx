"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { DatasetRequestForm } from "@/features/datasets/components/dataset-create-form";
import { DatasetsContainer } from "@/features/datasets/components/datasets-container";
import { DatasetsSearchBar } from "@/features/datasets/components/datasets-search-bar";
import type {
  DatasetRequest,
  DatasetSortFieldType,
} from "@/features/datasets/types";
import { Database, Plus } from "lucide-react";
import { useState } from "react";

export default function DatasetSearchPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [filters, setFilters] = useState<DatasetRequest>({
    limit: 20,
    sortBy: "name",
    sortOrder: "desc",
    query: undefined,
    dateCreated: undefined,
    dateLastUpdated: undefined,
  });

  const handleSort = (field: DatasetSortFieldType) => {
    setFilters((prev) => {
      const isSameField = prev.sortBy === field;
      const newOrder = isSameField && prev.sortOrder === "asc" ? "desc" : "asc";

      return {
        ...prev,
        sortBy: field,
        sortOrder: newOrder,
      };
    });
  };

  const updateFilters = (updates: Partial<DatasetRequest>) => {
    setFilters((prev) => ({ ...prev, ...updates }));
  };

  const handleSearch = (query: string) => {
    updateFilters({ query: query || undefined });
  };

  const clearAllFilters = () => {
    setFilters({
      limit: 20,
      sortBy: "name",
      sortOrder: "desc",
      query: undefined,
      dateCreated: undefined,
      dateLastUpdated: undefined,
    });
  };

  return (
    <div className="max-w-350 mx-auto px-6 relative pb-20">
      {/* 1. Header Row */}
      <div className="relative z-50 flex items-center justify-between pt-6 pb-2 bg-transparent">
        <div className="flex items-center gap-4">
          <div className="flex items-center p-1 rounded-lg bg-slate-900/50 border border-white/5 gap-1 shadow-lg">
            <SidebarTrigger className="h-8 w-8 text-slate-400 hover:text-indigo-400 transition-colors" />
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
              Registry
            </span>
            <div className="flex items-center gap-2">
              <Database size={10} className="text-indigo-400/50" />
              <span className="text-xs font-mono text-indigo-400/80">
                Datasets
              </span>
            </div>
          </div>
        </div>

        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="hover:border-indigo-500/40 hover:bg-indigo-500/10 hover:text-indigo-300"
            >
              <Plus size={14} className="mr-1.5" />
              Create Dataset
            </Button>
          </DialogTrigger>
          <DialogContent className="p-0 border-white/10 bg-transparent w-fit ring-0">
            <DialogTitle className="sr-only">Request Dataset</DialogTitle>
            <DatasetRequestForm onSuccess={() => setCreateOpen(false)} />
          </DialogContent>
        </Dialog>
      </div>

      {/* 2. Sticky Action Bar */}
      <div className="sticky top-0 z-40 py-4 bg-[#050507]/50 backdrop-blur-md">
        <DatasetsSearchBar
          filters={filters}
          onSearch={handleSearch}
          onFiltersChange={updateFilters}
          onClearFilters={clearAllFilters}
          isSearching={false}
        />
      </div>

      {/* 3. Content Area */}
      <div className="mt-4 relative z-10">
        <DatasetsContainer filters={filters} onSort={handleSort} />
      </div>
    </div>
  );
}
