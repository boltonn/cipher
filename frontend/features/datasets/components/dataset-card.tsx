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
      className="group flex flex-col rounded-xl bg-muted/40 border border-border/50 p-5 transition-all duration-300 hover:border-primary/40 hover:bg-muted/60"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Database size={14} className="text-primary shrink-0" />
          <h3 className="font-mono text-sm text-foreground truncate group-hover:text-primary transition-colors">
            {dataset.name}
          </h3>
        </div>
      </div>

      <p className="text-xs text-muted-foreground line-clamp-2 mb-4 min-h-8">
        {dataset.description || "No description"}
      </p>

      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-border/50">
        <Stat icon={<Files size={11} />} label="Files" value={formatCompactNumber(dataset.fileCount)} />
        <Stat icon={<HardDrive size={11} />} label="Size" value={formatBytes(dataset.totalSizeBytes)} />
        <Stat icon={<Tags size={11} />} label="Types" value={formatCompactNumber(dataset.filetypeCount)} />
      </div>

      <div className="mt-3 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
        Updated {new Date(dataset.dateLastUpdated).toLocaleDateString()}
      </div>
    </Link>
  );
}

const Stat = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) => (
  <div className="flex flex-col gap-0.5">
    <div className="flex items-center gap-1 text-muted-foreground">
      {icon}
      <span className="text-[11px] font-bold uppercase tracking-wide">{label}</span>
    </div>
    <span className="text-sm font-mono text-foreground">{value}</span>
  </div>
);
