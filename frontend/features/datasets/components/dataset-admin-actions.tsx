"use client";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDatasetUsers } from "@/features/datasets/api";
import { DatasetDialog } from "@/features/datasets/components/dataset-dialog";
import type { DatasetSummary } from "@/features/datasets/types";
import { useIsAdmin } from "@/features/users/hooks/use-me";
import { getInitials } from "@/features/users/utils";
import { cn } from "@/lib/utils";
import { Pencil, Plus, Users } from "lucide-react";
import { useState } from "react";

/** Admin-only controls share the rose `admin` token so they read as "only you see this". */
export const ADMIN_ICON_BUTTON = "h-7 text-admin/70 hover:bg-admin/10 hover:text-admin";

/** Fetched only while the popover is open. */
function DatasetMemberList({ datasetId }: { datasetId: string }) {
  const { data: members = [], isPending } = useDatasetUsers(datasetId);
  if (isPending) return <p className="px-2 py-1.5 text-xs text-muted-foreground">Loading…</p>;
  if (members.length === 0) {
    return (
      <p className="px-2 py-1.5 text-xs text-muted-foreground">
        No members -- only admins can open it.
      </p>
    );
  }
  return (
    <ul className="max-h-72 overflow-y-auto">
      {members.map((member) => (
        <li key={member.id} className="flex items-center gap-2 rounded-md px-2 py-1.5">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold">
            {getInitials(member.name)}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm text-foreground">{member.name}</span>
            <span className="block truncate text-xs text-muted-foreground">{member.email}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Admin-only row/card controls: member list and edit. Renders nothing for non-admins. */
export function DatasetAdminActions({
  dataset,
  className,
}: {
  dataset: DatasetSummary;
  className?: string;
}) {
  const isAdmin = useIsAdmin();
  const [isEditOpen, setIsEditOpen] = useState(false);
  if (!isAdmin) return null;

  return (
    // Keeps clicks (including from the portaled popover/dialog) from also opening the row.
    <span className={cn("flex items-center", className)} onClick={(event) => event.stopPropagation()}>
      <Popover>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="sm" className={cn(ADMIN_ICON_BUTTON, "gap-1 px-1.5")}>
                <Users size={13} />
                <span className="text-xs tabular-nums">{dataset.memberCount}</span>
              </Button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent>Members (admin only)</TooltipContent>
        </Tooltip>
        <PopoverContent align="end" className="w-72 gap-1 p-1.5">
          <p className="px-2 pt-1 pb-1.5 text-xs font-medium text-admin">
            Members of {dataset.name}
          </p>
          <DatasetMemberList datasetId={dataset.id} />
        </PopoverContent>
      </Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${dataset.name}`}
            onClick={() => setIsEditOpen(true)}
            className={cn(ADMIN_ICON_BUTTON, "w-7")}
          >
            <Pencil size={13} />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Edit (admin only)</TooltipContent>
      </Tooltip>
      <DatasetDialog dataset={dataset} isOpen={isEditOpen} onOpenChange={setIsEditOpen} />
    </span>
  );
}

/** Admin-only "New dataset" button for the datasets page header. */
export function NewDatasetButton() {
  const isAdmin = useIsAdmin();
  const [isOpen, setIsOpen] = useState(false);
  if (!isAdmin) return null;

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setIsOpen(true)}
        className="h-9 gap-1.5 border-admin/30 bg-admin/5 text-admin hover:bg-admin/10 hover:text-admin"
      >
        <Plus size={14} />
        New dataset
      </Button>
      <DatasetDialog isOpen={isOpen} onOpenChange={setIsOpen} />
    </>
  );
}
