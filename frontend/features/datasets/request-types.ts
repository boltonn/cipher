import { z } from "zod";

/** Analytics that can be requested against a dataset. Mirrors the backend `EnrichmentType`. */
export const ENRICHMENT_TYPES = [
  "text_extraction",
  "text_embedding",
  "image_embedding",
  "face_detection",
  "face_matching",
  "contact_extraction",
  "message_translation",
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
}

export interface AnalyticDef {
  type: EnrichmentType;
  label: string;
  description: string;
  params: readonly AnalyticParamDef[];
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
      { key: "chunkSize", label: "Chunk size (tokens)", kind: "number", min: 64, max: 4096, step: 32, defaultValue: 512 },
      { key: "maxPages", label: "Max pages / doc", kind: "number", min: 1, step: 1, defaultValue: "", optional: true },
    ],
  },
  {
    type: "text_embedding",
    label: "Text embedding",
    description: "Chunk and embed extracted text for semantic search.",
    params: [
      { key: "chunkSize", label: "Chunk size (tokens)", kind: "number", min: 64, max: 4096, step: 32, defaultValue: 512 },
      { key: "maxPages", label: "Max pages / doc", kind: "number", min: 1, step: 1, defaultValue: "", optional: true },
    ],
  },
  {
    type: "image_embedding",
    label: "Image embedding",
    description: "CLIP embeddings for image search and clustering.",
    params: [{ key: "batchSize", label: "Batch size", kind: "number", min: 1, max: 512, step: 1, defaultValue: 32 }],
  },
  {
    type: "face_detection",
    label: "Face detection",
    description: "Detect and embed faces in images.",
    params: [{ key: "batchSize", label: "Batch size", kind: "number", min: 1, max: 512, step: 1, defaultValue: 25 }],
  },
  {
    type: "face_matching",
    label: "Face matching",
    description: "Match detected faces against known persons.",
    params: [
      { key: "similarityThreshold", label: "Similarity threshold", kind: "number", min: 0, max: 1, step: 0.01, defaultValue: 0.5 },
      { key: "topK", label: "Top K candidates", kind: "number", min: 1, max: 100, step: 1, defaultValue: 10 },
    ],
  },
  {
    type: "contact_extraction",
    label: "Contact extraction",
    description: "Extract contacts and devices from parsed data.",
    params: [],
  },
  {
    type: "message_translation",
    label: "Message translation",
    description: "Translate messages into a target language.",
    params: [
      { key: "targetLanguage", label: "Target language (ISO)", kind: "text", defaultValue: "en" },
      { key: "batchSize", label: "Batch size", kind: "number", min: 1, max: 256, step: 1, defaultValue: 16 },
    ],
  },
] as const;

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
  contact_extraction: z.object({}),
  message_translation: z.object({
    targetLanguage: z.string().min(2).max(8),
    batchSize: z.number().int().min(1).max(256),
  }),
};

export const datasetRequestSchema = z.object({
  datasetId: z.string().trim().min(1, "Dataset ID is required").max(255),
  name: z.string().trim().max(255).optional(),
  reason: z.string().trim().min(10, "Add a sentence or two of context").max(5000),
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
  repo: string;
  issuesUrl: string;
}
