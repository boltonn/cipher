"use client";

import { formatBytes, formatCompactNumber } from "@/lib/utils";
import type { DatasetSummary } from "@/features/datasets/types";
import { Database, Files, HardDrive, Tags } from "lucide-react";
import Link from "next/link";

interface DatasetCardProps {
  dataset: DatasetSummary;
}

export function DatasetCard({ dataset }: DatasetCardProps) {
  return (
    <Link
      href={`/datasets/${dataset.id}`}
      className="group flex flex-col rounded-xl bg-slate-900/40 border border-white/5 p-5 transition-all duration-300 hover:border-indigo-500/40 hover:bg-slate-900/60"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Database size={14} className="text-indigo-400 shrink-0" />
          <h3 className="font-mono text-sm text-slate-200 truncate group-hover:text-indigo-300 transition-colors">
            {dataset.name}
          </h3>
        </div>
      </div>

      <p className="text-xs text-slate-500 line-clamp-2 mb-4 min-h-8">
        {dataset.description || "No description"}
      </p>

      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-white/5">
        <Stat icon={<Files size={11} />} label="Files" value={formatCompactNumber(dataset.fileCount)} />
        <Stat icon={<HardDrive size={11} />} label="Size" value={formatBytes(dataset.totalSizeBytes)} />
        <Stat icon={<Tags size={11} />} label="Types" value={formatCompactNumber(dataset.filetypeCount)} />
      </div>

      <div className="mt-3 text-[9px] font-bold uppercase tracking-widest text-slate-600">
        Updated {new Date(dataset.dateLastUpdated).toLocaleDateString()}
      </div>
    </Link>
  );
}

const Stat = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) => (
  <div className="flex flex-col gap-0.5">
    <div className="flex items-center gap-1 text-slate-600">
      {icon}
      <span className="text-[9px] font-bold uppercase tracking-widest">{label}</span>
    </div>
    <span className="text-sm font-mono text-slate-300">{value}</span>
  </div>
);
