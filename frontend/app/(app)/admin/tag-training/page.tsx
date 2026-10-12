"use client";

import { TagTrainingTable } from "@/features/tags/components/tag-training-table";

export default function AdminTagTrainingPage() {
  return (
    <div className="w-full max-w-6xl">
      <p className="mb-4 text-sm text-muted-foreground">
        Analyst labels per image tag. A tag needs enough positives before <code>cipher train-image-heads</code>{" "}
        trains a classifier for it; negatives (images marked &quot;not this tag&quot;) make that classifier sharper.
      </p>
      <TagTrainingTable />
    </div>
  );
}
