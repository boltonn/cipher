"use client";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { DateRangePicker } from "@/components/date-range-picker";
import { PageHeader } from "@/components/page-header";
import { PageLoading } from "@/components/page-loading";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useDataset,
  useDatasetStats,
  useDeleteDataset,
} from "@/features/datasets/api";
import { DatasetFileBrowser } from "@/features/datasets/components/dataset-file-browser";
import { DatasetDatabaseUsagePanel } from "@/features/database/components/dataset-database-usage";
import { DatasetMembers } from "@/features/datasets/components/dataset-members";
import { LOCKED_DATASET_HINT } from "@/features/datasets/components/dataset-lock";
import { DatasetDialog } from "@/features/datasets/components/dataset-dialog";
import { DatasetBriefCard } from "@/features/global-search/components/dataset-brief-card";
import { useRunSearch } from "@/features/global-search/api";
import { EMPTY_FILTERS } from "@/features/global-search/hooks/use-search-actions";
import { EnrichmentPipeline } from "@/features/datasets/components/enrichment-pipeline";
import { FiletypeBreakdownList } from "@/features/datasets/components/filetype-breakdown-list";
import { LoadHistogramChart } from "@/features/datasets/components/load-histogram-chart";
import { DatasetEntityBreakdown } from "@/features/entities/components/dataset-entity-breakdown";
import type {
  Dataset,
  HistogramGranularityType,
  LoadHistogramBucket,
} from "@/features/datasets/types";
import { useIsAdmin } from "@/features/users/hooks/use-me";
import { formatBytes, formatCompactNumber } from "@/lib/utils";
import { AnimatePresence, motion } from "motion/react";
import {
  BarChart3,
  Database,
  Files,
  Fingerprint,
  FolderOpen,
  HardDrive,
  Lock,
  PieChart,
  Pencil,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";

/** End-exclusive window covering the bucket's full day/week/month, for use as a date-range filter. */
function bucketToRange(
  dateBucket: string,
  granularity: HistogramGranularityType
) {
  const start = new Date(dateBucket);
  const end = new Date(start);
  if (granularity === "day") end.setDate(end.getDate() + 1);
  else if (granularity === "week") end.setDate(end.getDate() + 7);
  else end.setMonth(end.getMonth() + 1);
  end.setMilliseconds(end.getMilliseconds() - 1);
  return { from: start.toISOString(), to: end.toISOString() };
}

export default function DatasetDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: dataset, isPending } = useDataset(id);

  if (isPending) {
    return <PageLoading icon={Database} label="Loading dataset…" />;
  }
  if (!dataset?.hasAccess) {
    return <DatasetUnavailable dataset={dataset} />;
  }
  return <DatasetWorkspace dataset={dataset} />;
}

/** A dataset you can't open: discoverable but locked, or hidden from you entirely. */
function DatasetUnavailable({ dataset }: { dataset?: Dataset }) {
  return (
    <div className="max-w-xl mx-auto px-6 pt-24 text-center">
      <Lock className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
      <h1 className="text-lg font-semibold text-foreground">
        {dataset?.name ?? "Dataset unavailable"}
      </h1>
      {dataset?.description && (
        <p className="mt-1 text-sm text-muted-foreground">{dataset.description}</p>
      )}
      <p className="mt-4 text-sm text-muted-foreground">
        {dataset ? LOCKED_DATASET_HINT : "It doesn't exist or you don't have access to it."}
      </p>
      <Link
        href="/datasets"
        className="mt-6 inline-block text-xs font-medium text-primary hover:underline"
      >
        Back to datasets
      </Link>
    </div>
  );
}

function DatasetWorkspace({ dataset }: { dataset: Dataset }) {
  const id = dataset.id;
  const router = useRouter();
  const isAdmin = useIsAdmin();
  const runSearch = useRunSearch();

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const [granularity, setGranularity] =
    useState<HistogramGranularityType>("day");
  const [selectedBucket, setSelectedBucket] = useState<string | undefined>();
  const [filetype, setFiletype] = useState<string | undefined>();
  const [filetypeGroup, setFiletypeGroup] = useState<string | undefined>();

  const deleteDataset = useDeleteDataset(() => router.push("/datasets"));
  const { data: stats, isPending: statsPending } = useDatasetStats(id, {
    dateFrom: range.from,
    dateTo: range.to,
    granularity,
    filetype,
    filetypeGroup,
  });

  const hasCrossFilters = !!filetype || !!filetypeGroup || !!selectedBucket;

  const handleSelectBucket = (bucket: LoadHistogramBucket) => {
    if (selectedBucket === bucket.dateBucket) {
      setSelectedBucket(undefined);
      setRange({});
      return;
    }
    setSelectedBucket(bucket.dateBucket);
    setRange(bucketToRange(bucket.dateBucket, granularity));
  };

  const handleSelectFiletype = (value: string | undefined) => {
    setFiletype(value);
    setFiletypeGroup(undefined);
  };

  const handleSelectFiletypeGroup = (value: string | undefined) => {
    setFiletypeGroup(value);
    setFiletype(undefined);
  };

  const clearCrossFilters = () => {
    setFiletype(undefined);
    setFiletypeGroup(undefined);
    setSelectedBucket(undefined);
    setRange({});
  };

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20 pt-5">
      <PageHeader>
        <div className="flex flex-col">
          <Link
            href="/datasets"
            className="text-xs font-medium text-muted-foreground hover:text-primary transition-colors"
          >
            Registry
          </Link>
          <span className="text-xs font-mono text-primary/80">
            {dataset.name}
          </span>
        </div>
      </PageHeader>

      {/* Identity header */}
      <div className="mt-4 rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-6 flex items-start justify-between gap-4">
        <div className="flex flex-col gap-2 min-w-0">
          <div className="flex items-center gap-2.5">
            <Database size={16} className="text-primary" />
            <h1 className="text-xl font-bold text-white">{dataset.name}</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            {dataset.description || "No description"}
          </p>
        </div>
        {isAdmin && (
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsEditOpen(true)}
            className="h-9 gap-2 border-admin/30 bg-admin/5 text-xs font-medium text-admin hover:bg-admin/10 hover:text-admin"
          >
            <Pencil size={14} />
            Edit
          </Button>
          {/* Destructive + irreversible: kept available but visually quiet, so
              it doesn't read as a peer of Edit. */}
          <ConfirmDialog
            trigger={
              <Button
                variant="ghost"
                size="icon"
                aria-label="Delete dataset"
                className="h-9 w-9 text-admin/60 hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 size={14} />
              </Button>
            }
            title="Delete this dataset?"
            description={
              <>
                This permanently deletes{" "}
                <strong className="text-foreground">{dataset.name}</strong> and
                every file, extracted/embedded text, face, image, and comment
                scoped to it -- including its entries in the search index. This
                can&apos;t be undone.
              </>
            }
            confirmLabel="Delete Dataset"
            isPending={deleteDataset.isPending}
            onConfirm={() => deleteDataset.mutate(id)}
          />
        </div>
        )}
      </div>

      <DatasetDialog
        dataset={dataset}
        isOpen={isEditOpen}
        onOpenChange={setIsEditOpen}
      />

      <div className="mt-4">
        <DatasetBriefCard
          datasetIds={[id]}
          onSearch={(query) =>
            runSearch.mutate({
              query,
              datasetIds: [id],
              filters: EMPTY_FILTERS,
            })
          }
        />
      </div>

      <EnrichmentPipeline datasetId={id} />

      {isAdmin && (
        <>
          <DatasetMembers datasetId={id} />
          <DatasetDatabaseUsagePanel datasetId={id} />
        </>
      )}

      {/* Date range + granularity filter */}
      <div className="mt-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <BarChart3 size={14} className="text-primary" />
          <h2 className="text-[11px] font-semibold uppercase tracking-wide">
            Files Loaded Over Time
          </h2>
          <AnimatePresence>
            {hasCrossFilters && (
              <motion.button
                type="button"
                onClick={clearCrossFilters}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-primary hover:bg-primary/20 hover:text-primary"
              >
                <X size={11} />
                Clear filters
              </motion.button>
            )}
          </AnimatePresence>
        </div>
        <div className="flex items-center gap-2">
          <DateRangePicker
            value={range}
            onChange={(value) => {
              setRange(value);
              setSelectedBucket(undefined);
            }}
            className="w-60"
          />
          <Select
            value={granularity}
            onValueChange={(v) => setGranularity(v as HistogramGranularityType)}
          >
            <SelectTrigger className="w-28 text-xs bg-muted/40 border-border">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="day">Daily</SelectItem>
              <SelectItem value="week">Weekly</SelectItem>
              <SelectItem value="month">Monthly</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Stats + histogram */}
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-1 grid grid-cols-2 lg:grid-cols-1 gap-4">
          <StatCard
            icon={<Files size={14} />}
            label="Files in Range"
            value={
              statsPending ? "—" : formatCompactNumber(stats?.totalFiles ?? 0)
            }
          />
          <StatCard
            icon={<HardDrive size={14} />}
            label="Size in Range"
            value={statsPending ? "—" : formatBytes(stats?.totalSizeBytes ?? 0)}
          />
        </div>
        <div className="lg:col-span-3 rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-6">
          {statsPending ? (
            <div className="h-48 flex items-center justify-center text-xs text-muted-foreground">
              Loading...
            </div>
          ) : (
            <LoadHistogramChart
              buckets={stats?.loadedOverTime ?? []}
              granularity={granularity}
              selectedBucket={selectedBucket}
              onSelectBucket={handleSelectBucket}
            />
          )}
        </div>
      </div>

      {/* Breakdowns */}
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-6">
          <div className="flex items-center gap-2 text-muted-foreground mb-4">
            <PieChart size={14} className="text-primary" />
            <h2 className="text-[11px] font-semibold uppercase tracking-wide">
              By Filetype
            </h2>
          </div>
          {statsPending ? (
            <div className="h-80 flex items-center justify-center text-xs text-muted-foreground">
              Loading...
            </div>
          ) : (
            <FiletypeBreakdownList
              items={stats?.byFiletype ?? []}
              selected={filetype}
              onSelect={handleSelectFiletype}
            />
          )}
        </div>
        <div className="rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-6">
          <div className="flex items-center gap-2 text-muted-foreground mb-4">
            <PieChart size={14} className="text-primary" />
            <h2 className="text-[11px] font-semibold uppercase tracking-wide">
              By Filetype Group
            </h2>
          </div>
          {statsPending ? (
            <div className="h-80 flex items-center justify-center text-xs text-muted-foreground">
              Loading...
            </div>
          ) : (
            <FiletypeBreakdownList
              items={stats?.byFiletypeGroup ?? []}
              selected={filetypeGroup}
              onSelect={handleSelectFiletypeGroup}
            />
          )}
        </div>
      </div>

      {/* Entities / selectors */}
      <div className="mt-6 rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Fingerprint size={14} className="text-primary" />
            <h2 className="text-[11px] font-semibold uppercase tracking-wide">
              Entities &amp; Selectors
            </h2>
          </div>
          <Link
            href={`/entities?datasetId=${id}`}
            className="text-[11px] font-medium text-primary hover:underline"
          >
            View all →
          </Link>
        </div>
        <DatasetEntityBreakdown datasetId={id} />
      </div>

      {/* File browser */}
      <div className="mt-6 rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-6">
        <div className="flex items-center gap-2 text-muted-foreground mb-4">
          <FolderOpen size={14} className="text-primary" />
          <h2 className="text-[11px] font-semibold uppercase tracking-wide">
            Files
          </h2>
        </div>
        <DatasetFileBrowser
          datasetId={id}
          filetype={filetype}
          filetypeGroup={filetypeGroup}
        />
      </div>
    </div>
  );
}

const StatCard = ({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) => (
  <div className="rounded-2xl bg-muted/40 backdrop-blur-2xl border border-border p-4 flex flex-col gap-1.5 overflow-hidden">
    <div className="flex items-center gap-1.5 text-muted-foreground">
      {icon}
      <span className="text-[11px] font-bold uppercase tracking-wide">
        {label}
      </span>
    </div>
    <AnimatePresence mode="wait">
      <motion.span
        key={value}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.15 }}
        className="text-lg font-mono text-foreground"
      >
        {value}
      </motion.span>
    </AnimatePresence>
  </div>
);
