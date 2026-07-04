"use client";

import { DateRangePicker } from "@/components/date-range-picker";
import { SidebarTrigger } from "@/components/ui/sidebar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDataset, useDatasetStats } from "@/features/datasets/api";
import { FiletypeBreakdownList } from "@/features/datasets/components/filetype-breakdown-list";
import { LoadHistogramChart } from "@/features/datasets/components/load-histogram-chart";
import type { HistogramGranularityType } from "@/features/datasets/types";
import { formatBytes, formatCompactNumber } from "@/lib/utils";
import { BarChart3, Database, Files, HardDrive, PieChart } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";

export default function DatasetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const [granularity, setGranularity] = useState<HistogramGranularityType>("day");

  const { data: dataset, isPending: datasetPending } = useDataset(id);
  const { data: stats, isPending: statsPending } = useDatasetStats(id, {
    dateFrom: range.from,
    dateTo: range.to,
    granularity,
  });

  if (datasetPending || !dataset) {
    return (
      <div className="flex items-center justify-center py-48 text-slate-500">
        <Database className="h-8 w-8 animate-pulse text-indigo-500/40" />
      </div>
    );
  }

  return (
    <div className="max-w-350 mx-auto px-6 relative pb-20">
      {/* Header */}
      <div className="sticky top-0 z-30 flex items-center justify-between pt-6 pb-2 bg-[#050507]/90">
        <div className="flex items-center gap-4">
          <SidebarTrigger className="h-9 w-9 text-slate-400 hover:text-indigo-400" />
          <div className="flex flex-col">
            <Link
              href="/datasets"
              className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] hover:text-indigo-400 transition-colors"
            >
              Registry
            </Link>
            <span className="text-xs font-mono text-indigo-400/80">{dataset.name}</span>
          </div>
        </div>
      </div>

      {/* Identity header */}
      <div className="mt-4 rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6 flex flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <Database size={16} className="text-indigo-400" />
          <h1 className="text-xl font-bold text-white">{dataset.name}</h1>
        </div>
        <p className="text-sm text-slate-400">{dataset.description || "No description"}</p>
      </div>

      {/* Date range + granularity filter */}
      <div className="mt-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-slate-400">
          <BarChart3 size={14} className="text-indigo-400" />
          <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">Files Loaded Over Time</h2>
        </div>
        <div className="flex items-center gap-2">
          <DateRangePicker value={range} onChange={setRange} className="w-64" />
          <Select value={granularity} onValueChange={(v) => setGranularity(v as HistogramGranularityType)}>
            <SelectTrigger className="w-28 h-9 text-xs bg-slate-900/40 border-white/10">
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
            value={statsPending ? "—" : formatCompactNumber(stats?.totalFiles ?? 0)}
          />
          <StatCard
            icon={<HardDrive size={14} />}
            label="Size in Range"
            value={statsPending ? "—" : formatBytes(stats?.totalSizeBytes ?? 0)}
          />
        </div>
        <div className="lg:col-span-3 rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6">
          {statsPending ? (
            <div className="h-48 flex items-center justify-center text-xs text-slate-600">Loading...</div>
          ) : (
            <LoadHistogramChart buckets={stats?.loadedOverTime ?? []} granularity={granularity} />
          )}
        </div>
      </div>

      {/* Breakdowns */}
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6">
          <div className="flex items-center gap-2 text-slate-400 mb-4">
            <PieChart size={14} className="text-indigo-400" />
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">By Filetype</h2>
          </div>
          {statsPending ? (
            <div className="h-24 flex items-center justify-center text-xs text-slate-600">Loading...</div>
          ) : (
            <FiletypeBreakdownList items={stats?.byFiletype ?? []} />
          )}
        </div>
        <div className="rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-6">
          <div className="flex items-center gap-2 text-slate-400 mb-4">
            <PieChart size={14} className="text-indigo-400" />
            <h2 className="text-[10px] font-black uppercase tracking-[0.2em]">By Filetype Group</h2>
          </div>
          {statsPending ? (
            <div className="h-24 flex items-center justify-center text-xs text-slate-600">Loading...</div>
          ) : (
            <FiletypeBreakdownList items={stats?.byFiletypeGroup ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}

const StatCard = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) => (
  <div className="rounded-2xl bg-slate-950/40 backdrop-blur-2xl border border-white/10 p-4 flex flex-col gap-1.5">
    <div className="flex items-center gap-1.5 text-slate-500">
      {icon}
      <span className="text-[9px] font-bold uppercase tracking-widest">{label}</span>
    </div>
    <span className="text-lg font-mono text-slate-200">{value}</span>
  </div>
);
