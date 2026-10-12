"use client";

import { DatasetAdminActions } from "@/features/datasets/components/dataset-admin-actions";
import { DatasetLock } from "@/features/datasets/components/dataset-lock";
import { cn, formatBytes, formatCompactNumber } from "@/lib/utils";
import type { DatasetSummary } from "@/features/datasets/types";
import { Database, Files, HardDrive, Tags } from "lucide-react";
import Link from "next/link";

interface DatasetCardProps {
  dataset: DatasetSummary;
}

export function DatasetCard({ dataset }: DatasetCardProps) {
  const className =
    "group flex h-full flex-col rounded-xl bg-muted/40 border border-border/50 p-5 transition-all duration-300";
  const body = <DatasetCardBody dataset={dataset} />;

  return (
    <div className="relative h-full">
      {dataset.hasAccess ? (
        <Link
          href={`/datasets/${dataset.id}`}
          className={cn(className, "hover:border-primary/40 hover:bg-muted/60")}
        >
          {body}
        </Link>
      ) : (
        <div className={cn(className, "opacity-70")}>{body}</div>
      )}
      <DatasetAdminActions dataset={dataset} className="absolute right-4 bottom-5" />
    </div>
  );
}

function DatasetCardBody({ dataset }: DatasetCardProps) {
  return (
    <>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Database size={14} className="text-primary shrink-0" />
          <h3
            title={dataset.name}
            className="font-mono text-sm text-foreground truncate group-hover:text-primary transition-colors"
          >
            {dataset.name}
          </h3>
          {!dataset.hasAccess && <DatasetLock />}
        </div>
      </div>

      <p className="text-xs text-muted-foreground line-clamp-2 mb-4 min-h-8">
        {dataset.description || "No description"}
      </p>

      <div className="flex justify-between gap-3 pt-3 border-t border-border/50">
        <Stat icon={<Files size={11} />} label="Files" value={formatCompactNumber(dataset.fileCount)} />
        <Stat icon={<HardDrive size={11} />} label="Size" value={formatBytes(dataset.totalSizeBytes)} />
        <Stat icon={<Tags size={11} />} label="Types" value={formatCompactNumber(dataset.filetypeCount)} />
      </div>

      <div className="mt-auto flex h-7 items-center pt-3 pr-20 text-[11px] font-bold uppercase tracking-wide text-muted-foreground box-content">
        Updated {new Date(dataset.dateLastUpdated).toLocaleDateString()}
      </div>
    </>
  );
}

const Stat = ({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) => (
  <div className="flex flex-col gap-0.5">
    <div className="flex items-center gap-1 text-muted-foreground">
      {icon}
      <span className="text-[11px] font-bold uppercase tracking-wide">{label}</span>
    </div>
    <span className="whitespace-nowrap text-sm font-mono text-foreground">{value}</span>
  </div>
);
