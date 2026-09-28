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
import { EditDatasetDialog } from "@/features/datasets/components/edit-dataset-dialog";
import { EnrichmentEstimates } from "@/features/datasets/components/enrichment-estimates";
import { EnrichmentPipeline } from "@/features/datasets/components/enrichment-pipeline";
import { FiletypeBreakdownList } from "@/features/datasets/components/filetype-breakdown-list";
import { LoadHistogramChart } from "@/features/datasets/components/load-histogram-chart";
import { DatasetEntityBreakdown } from "@/features/entities/components/dataset-entity-breakdown";
import type {
  HistogramGranularityType,
  LoadHistogramBucket,
} from "@/features/datasets/types";
import { formatBytes, formatCompactNumber } from "@/lib/utils";
import { AnimatePresence, motion } from "motion/react";
import {
  BarChart3,
  Database,
  Files,
  Fingerprint,
  FolderOpen,
  HardDrive,
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
  const router = useRouter();

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const [granularity, setGranularity] =
    useState<HistogramGranularityType>("day");
  const [selectedBucket, setSelectedBucket] = useState<string | undefined>();
  const [filetype, setFiletype] = useState<string | undefined>();
  const [filetypeGroup, setFiletypeGroup] = useState<string | undefined>();

  const { data: dataset, isPending: datasetPending } = useDataset(id);
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

  if (datasetPending || !dataset) {
    return <PageLoading icon={Database} label="Loading dataset…" />;
  }

  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20 pt-5">
      <PageHeader>
        <div className="flex flex-col">
          <Link
            href="/datasets"
            className="text-[10px] font-black text-muted-foreground uppercase tracking-[0.2em] hover:text-primary transition-colors"
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
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsEditOpen(true)}
            className="h-9 bg-muted/40 border-border text-muted-foreground hover:text-primary uppercase text-[10px] font-bold tracking-widest gap-2"
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
                className="h-9 w-9 text-muted-foreground/70 hover:bg-destructive/10 hover:text-destructive"
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
      </div>

      <EditDatasetDialog
        dataset={dataset}
        isOpen={isEditOpen}
        onOpenChange={setIsEditOpen}
      />

      <EnrichmentPipeline datasetId={id} />

      <EnrichmentEstimates datasetId={id} />

      {/* Date range + granularity filter */}
      <div className="mt-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <BarChart3 size={14} className="text-primary" />
          <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
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
                className="flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-primary hover:bg-primary/20 hover:text-primary"
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
            className="w-64"
          />
          <Select
            value={granularity}
            onValueChange={(v) => setGranularity(v as HistogramGranularityType)}
          >
            <SelectTrigger className="w-28 data-[size=default]:h-9 text-xs bg-muted/40 border-border">
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
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
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
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
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
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
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
          <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
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
      <span className="text-[9px] font-bold uppercase tracking-widest">
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
