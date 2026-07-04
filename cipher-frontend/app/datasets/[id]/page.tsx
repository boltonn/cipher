"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useDataset, useDatasetStats } from "@/features/datasets/api";
import { EditDatasetDialog } from "@/features/datasets/components/edit-dataset-dialog";
import { FiletypeBreakdownList } from "@/features/datasets/components/filetype-breakdown-list";
import { LoadHistogramChart } from "@/features/datasets/components/load-histogram-chart";
import type { HistogramGranularityType, LoadHistogramBucket } from "@/features/datasets/types";
import { formatBytes, formatCompactNumber } from "@/lib/utils";
import { AnimatePresence, motion } from "motion/react";
import { BarChart3, Database, Files, HardDrive, PieChart, Pencil, X } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";

/** End-exclusive window covering the bucket's full day/week/month, for use as a date-range filter. */
function bucketToRange(dateBucket: string, granularity: HistogramGranularityType) {
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

  const [isEditOpen, setIsEditOpen] = useState(false);
  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const [granularity, setGranularity] =
    useState<HistogramGranularityType>("day");
  const [selectedBucket, setSelectedBucket] = useState<string | undefined>();
  const [filetype, setFiletype] = useState<string | undefined>();
  const [filetypeGroup, setFiletypeGroup] = useState<string | undefined>();

  const { data: dataset, isPending: datasetPending } = useDataset(id);
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
    return (
      <div className="flex items-center justify-center py-48 text-slate-500">
        <Database className="h-8 w-8 animate-pulse text-indigo-500/40" />
      </div>
    );
  }

  return (
    <div className="max-w-350 mx-auto px-6 relative pb-20">
      <PageHeader>
        <div className="flex items-center gap-4">
          <SidebarTrigger className="h-9 w-9 text-slate-400 hover:text-indigo-400" />
          <div className="flex flex-col">
            <Link
              href="/datasets"
              className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] hover:text-indigo-400 transition-colors"
            >
              Registry
            </Link>
            <span className="text-xs font-mono text-indigo-400/80">
              {dataset.name}
            </span>
          </div>
        </div>
      </PageHeader>

      {/* Identity header */}
      <div className="mt-4 rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6 flex items-start justify-between gap-4">
        <div className="flex flex-col gap-2 min-w-0">
          <div className="flex items-center gap-2.5">
            <Database size={16} className="text-indigo-400" />
            <h1 className="text-xl font-bold text-white">{dataset.name}</h1>
          </div>
          <p className="text-sm text-slate-400">
            {dataset.description || "No description"}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setIsEditOpen(true)}
          className="h-9 shrink-0 bg-slate-900/40 border-white/10 text-slate-400 hover:text-indigo-400 uppercase text-[10px] font-bold tracking-widest gap-2"
        >
          <Pencil size={14} />
          Edit
        </Button>
      </div>

      <EditDatasetDialog dataset={dataset} isOpen={isEditOpen} onOpenChange={setIsEditOpen} />

      {/* Date range + granularity filter */}
      <div className="mt-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-slate-400">
          <BarChart3 size={14} className="text-indigo-400" />
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
                className="flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-indigo-300 hover:bg-indigo-500/20 hover:text-indigo-200"
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
            <SelectTrigger className="w-28 data-[size=default]:h-9 text-xs bg-slate-900/40 border-white/10">
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
        <div className="lg:col-span-3 rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6">
          {statsPending ? (
            <div className="h-48 flex items-center justify-center text-xs text-slate-600">
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
        <div className="rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6">
          <div className="flex items-center gap-2 text-slate-400 mb-4">
            <PieChart size={14} className="text-indigo-400" />
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
              By Filetype
            </h2>
          </div>
          {statsPending ? (
            <div className="h-24 flex items-center justify-center text-xs text-slate-600">
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
        <div className="rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6">
          <div className="flex items-center gap-2 text-slate-400 mb-4">
            <PieChart size={14} className="text-indigo-400" />
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">
              By Filetype Group
            </h2>
          </div>
          {statsPending ? (
            <div className="h-24 flex items-center justify-center text-xs text-slate-600">
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
  <div className="rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-4 flex flex-col gap-1.5 overflow-hidden">
    <div className="flex items-center gap-1.5 text-slate-500">
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
        className="text-lg font-mono text-slate-200"
      >
        {value}
      </motion.span>
    </AnimatePresence>
  </div>
);
