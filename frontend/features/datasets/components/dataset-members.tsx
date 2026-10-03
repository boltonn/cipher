"use client";

import { useDatasetUsers } from "@/features/datasets/api";
import { getInitials } from "@/features/users/utils";
import { Users } from "lucide-react";

/** Who has access to a dataset; membership is managed by admins under Settings. */
export function DatasetMembers({ datasetId }: { datasetId: string }) {
  const { data: members = [], isPending } = useDatasetUsers(datasetId);

  return (
    <div className="mt-6 rounded-2xl border border-border bg-muted/40 p-4">
      <div className="mb-3 flex items-center gap-2 text-muted-foreground">
        <Users size={14} className="text-primary" />
        <h2 className="text-[11px] font-semibold uppercase tracking-wide">
          Members
        </h2>
        <span className="text-[11px]">{isPending ? "" : members.length}</span>
      </div>
      {!isPending && members.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No members yet -- only admins can see this dataset.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {members.map((member) => (
            <span
              key={member.id}
              title={member.email}
              className="flex items-center gap-2 rounded-full border border-border/60 py-1 pl-1 pr-3 text-xs text-foreground"
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[10px] font-semibold">
                {getInitials(member.name)}
              </span>
              {member.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
