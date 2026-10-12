"use client";

import { Switch } from "@/components/ui/switch";
import { SOURCE_ORIGIN } from "@/features/search/components/source-filter";
import { useSourceFacets } from "@/features/search/hooks/use-source-facets";

/** The mail client's non-personal inbox categories (Gmail tabs) a reviewer may want out of the way. */
const HIDEABLE_SOURCE_TAGS = ["promotions", "updates", "social", "forums"];

/**
 * Hide review items whose only evidence is in mail the client itself filed under promotions,
 * updates, social or forums. Extraction still runs on everything; this only narrows the queue.
 * Renders nothing when the datasets carry none of those source tags.
 */
export function SourceTagsToggle({
  datasetIds,
  value,
  onChange,
}: {
  datasetIds: string[];
  value: string[] | undefined;
  onChange: (excludeSourceTags: string[] | undefined) => void;
}) {
  const { data: facets } = useSourceFacets(datasetIds);
  const present = HIDEABLE_SOURCE_TAGS.filter((tag) =>
    facets?.sourceTags?.some((facet) => facet.value === tag)
  );
  if (!present.length) return null;

  return (
    <label
      className="flex items-center gap-2 text-[11px] text-muted-foreground"
      title={SOURCE_ORIGIN}
    >
      <Switch
        size="sm"
        checked={!!value?.length}
        onCheckedChange={(checked) => onChange(checked ? present : undefined)}
      />
      Hide {present.join(", ")}
    </label>
  );
}
