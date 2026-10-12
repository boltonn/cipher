/** Search deep link: every file with a mention of `value` (a name group, an IP, ...), opened for review. */
export function mentionSearchHref(value: string, datasetId?: string | null) {
  const params = new URLSearchParams({ mentionValue: value });
  if (datasetId) params.set("datasetId", datasetId);
  return `/search/text?${params}`;
}
