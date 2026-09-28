import { z } from "zod";

/** Analytics that can be requested against a dataset. Mirrors the backend `EnrichmentType`. */
export const ENRICHMENT_TYPES = [
  "text_extraction",
  "text_embedding",
  "image_embedding",
  "face_detection",
  "face_matching",
  "face_clustering",
] as const;

export type EnrichmentType = (typeof ENRICHMENT_TYPES)[number];

export type AnalyticParamKind = "number" | "select" | "text";

export interface AnalyticParamDef {
  /** camelCase key, matches the backend parameter alias. */
  key: string;
  label: string;
  kind: AnalyticParamKind;
  defaultValue: number | string;
  min?: number;
  max?: number;
  step?: number;
  options?: readonly string[];
  optional?: boolean;
  /** Which emitted enrichment this param belongs to. Defaults to the def's `type`. */
  owner?: EnrichmentType;
}

export interface AnalyticDef {
  /** UI identity + the default emitted enrichment type. */
  type: EnrichmentType;
  label: string;
  description: string;
  params: readonly AnalyticParamDef[];
  /**
   * Enrichment payload entries this one toggle expands to on submit. Defaults
   * to `[type]`; a composite like "Face recognition" emits several.
   */
  emits?: readonly EnrichmentType[];
  /**
   * Analytics that must run first for this one to produce anything. Mirrors the
   * backend `ENRICHMENT_DEPENDENCIES` (source of truth; also at
   * `GET /enrichments/config`). Enabling this analytic auto-enables these.
   */
  dependsOn?: readonly EnrichmentType[];
}

/** Form metadata for each analytic. Parameter shapes mirror `cipher.schemas.dataset_request`. */
export const ANALYTICS: readonly AnalyticDef[] = [
  {
    type: "text_extraction",
    label: "Text extraction",
    description: "Pull text (and OCR) out of documents.",
    params: [
      {
        key: "chunker",
        label: "Chunker",
        kind: "select",
        options: ["kreuzberg", "clir"],
        defaultValue: "kreuzberg",
      },
      {
        key: "chunkSize",
        label: "Chunk size (tokens)",
        kind: "number",
        min: 64,
        max: 4096,
        step: 32,
        defaultValue: 512,
      },
      {
        key: "maxPages",
        label: "Max pages / doc",
        kind: "number",
        min: 1,
        step: 1,
        defaultValue: "",
        optional: true,
      },
    ],
  },
  {
    type: "text_embedding",
    label: "Text embedding",
    description: "Chunk and embed extracted text for semantic search.",
    dependsOn: ["text_extraction"],
    params: [
      {
        key: "chunkSize",
        label: "Chunk size (tokens)",
        kind: "number",
        min: 64,
        max: 4096,
        step: 32,
        defaultValue: 512,
      },
      {
        key: "maxPages",
        label: "Max pages / doc",
        kind: "number",
        min: 1,
        step: 1,
        defaultValue: "",
        optional: true,
      },
    ],
  },
  {
    type: "image_embedding",
    label: "Image embedding",
    description: "CLIP embeddings for image search and clustering.",
    params: [
      {
        key: "batchSize",
        label: "Batch size",
        kind: "number",
        min: 1,
        max: 512,
        step: 1,
        defaultValue: 32,
      },
    ],
  },
  {
    type: "face_detection",
    label: "Face recognition",
    description: "Detect faces in images and match them against known persons.",
    emits: ["face_detection", "face_matching"],
    params: [
      {
        key: "batchSize",
        label: "Batch size",
        kind: "number",
        min: 1,
        max: 512,
        step: 1,
        defaultValue: 25,
        owner: "face_detection",
      },
      {
        key: "similarityThreshold",
        label: "Match threshold",
        kind: "number",
        min: 0,
        max: 1,
        step: 0.01,
        defaultValue: 0.5,
        owner: "face_matching",
      },
      {
        key: "topK",
        label: "Top K candidates",
        kind: "number",
        min: 1,
        max: 100,
        step: 1,
        defaultValue: 10,
        owner: "face_matching",
      },
    ],
  },
  {
    type: "face_clustering",
    label: "Face clustering",
    description:
      "Group unassigned faces into unnamed person identities. Small clusters stay unassigned.",
    dependsOn: ["face_detection"],
    params: [
      {
        key: "similarity",
        label: "Cluster similarity",
        kind: "number",
        min: 0,
        max: 1,
        step: 0.01,
        defaultValue: 0.61,
      },
      {
        key: "minImages",
        label: "Min images per person",
        kind: "number",
        min: 1,
        max: 1000,
        step: 1,
        defaultValue: 3,
      },
      {
        key: "minFaces",
        label: "Min faces per person",
        kind: "number",
        min: 2,
        max: 1000,
        step: 1,
        defaultValue: 2,
      },
      {
        key: "k",
        label: "Neighbours per face",
        kind: "number",
        min: 2,
        max: 200,
        step: 1,
        defaultValue: 20,
      },
    ],
  },
] as const;

const ANALYTIC_BY_TYPE: Record<string, AnalyticDef> = Object.fromEntries(
  ANALYTICS.map((a) => [a.type, a])
);

/** `type` plus every analytic it (transitively) `dependsOn`. */
export function withPrerequisites(type: EnrichmentType): EnrichmentType[] {
  const out = new Set<EnrichmentType>();
  const visit = (t: EnrichmentType) => {
    if (out.has(t)) return;
    out.add(t);
    for (const dep of ANALYTIC_BY_TYPE[t]?.dependsOn ?? []) visit(dep);
  };
  visit(type);
  return [...out];
}

/** Every analytic that (transitively) `dependsOn` `type`. */
export function dependentsOf(type: EnrichmentType): EnrichmentType[] {
  const out = new Set<EnrichmentType>();
  const visit = (t: EnrichmentType) => {
    for (const a of ANALYTICS) {
      if (!out.has(a.type) && (a.dependsOn ?? []).includes(t)) {
        out.add(a.type);
        visit(a.type);
      }
    }
  };
  visit(type);
  return [...out];
}

export const analyticLabel = (type: EnrichmentType): string =>
  ANALYTIC_BY_TYPE[type]?.label ?? type.replace(/_/g, " ");

/** Per-analytic parameter validation, keyed by enrichment type. */
export const paramSchemas: Record<EnrichmentType, z.ZodType> = {
  text_extraction: z.object({
    chunker: z.enum(["kreuzberg", "clir"]),
    chunkSize: z.number().int().min(64).max(4096),
    maxPages: z.number().int().min(1).optional(),
  }),
  text_embedding: z.object({
    chunkSize: z.number().int().min(64).max(4096),
    maxPages: z.number().int().min(1).optional(),
  }),
  image_embedding: z.object({ batchSize: z.number().int().min(1).max(512) }),
  face_detection: z.object({ batchSize: z.number().int().min(1).max(512) }),
  face_matching: z.object({
    similarityThreshold: z.number().min(0).max(1),
    topK: z.number().int().min(1).max(100),
  }),
  face_clustering: z.object({
    similarity: z.number().min(0).max(1),
    minImages: z.number().int().min(1).max(1000),
    minFaces: z.number().int().min(2).max(1000),
    k: z.number().int().min(2).max(200),
  }),
};

export const datasetRequestSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(255),
  datasetId: z.string().trim().min(1, "Dataset ID is required").max(255),
  description: z.string().trim().max(5000).optional(),
  analytics: z
    .array(
      z.object({
        enrichmentType: z.enum(ENRICHMENT_TYPES),
        parameters: z.record(z.string(), z.unknown()),
      })
    )
    .min(1, "Select at least one analytic"),
});

export type DatasetRequestInput = z.infer<typeof datasetRequestSchema>;

export interface DatasetRequestResult {
  issueNumber: number;
  issueUrl: string;
  issuesUrl: string;
}

export interface DatasetRequestConfig {
  configured: boolean;
  repo?: string;
  issuesUrl?: string;
}

/* -------------------------------------------------------------------------- */
/*  Enrichment time estimates (mirrors backend `cipher.schemas.estimation`)   */
/* -------------------------------------------------------------------------- */

export type RunDevice = "cpu" | "cuda" | "mps" | "na";
export type EstimateConfidence = "measured" | "seeded" | "none";

export interface EnrichmentWorkload {
  enrichmentType: string;
  unit: string;
  unitCount: number;
  byteCount: number;
  estimable: boolean;
  note: string | null;
}

export interface EnrichmentEstimate {
  enrichmentType: string;
  eligible: EnrichmentWorkload;
  estimateSeconds: number | null;
  lowSeconds: number | null;
  highSeconds: number | null;
  confidence: EstimateConfidence;
  basis: string;
  prerequisites: string[];
  /** 0..1, share already complete. */
  progress: number;
}

export interface DatasetEnrichmentEstimates {
  datasetId: string;
  isStaged: boolean;
  device: RunDevice;
  dateGenerated: string;
  items: EnrichmentEstimate[];
}

/** Compact human duration: `~45s`, `~12 min`, `~2.5 h`, `~1.4 d`. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "n/a";
  if (seconds < 90) return `~${Math.round(seconds)}s`;
  const minutes = seconds / 60;
  if (minutes < 90) return `~${Math.round(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 36) return `~${hours.toFixed(1)} h`;
  return `~${(hours / 24).toFixed(1)} d`;
}
