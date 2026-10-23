import { z } from "zod";
import { humanize } from "@/lib/utils";

/** Analytics that can be requested against a dataset. Mirrors the backend `EnrichmentType`. */
export const ENRICHMENT_TYPES = [
  "archiveExtraction",
  "textExtraction",
  "ocr",
  "textEmbedding",
  "imageEmbedding",
  "exifLocation",
  "faceDetection",
  "faceMatching",
  "faceClustering",
  "contactExtraction",
  "selectorExtraction",
  "entityExtraction",
  "relationshipExtraction",
  "eventExtraction",
  "signatureExtraction",
  "tableExtraction",
  "textSummarization",
] as const;

export type EnrichmentType = (typeof ENRICHMENT_TYPES)[number];

export type AnalyticParamKind =
  | "number"
  | "select"
  | "text"
  | "groups"
  | "boolean";

/** Filetype groups a text analytic can read. Spreadsheets (`table`) are off by default: they're mapped column by column. */
export const TEXT_GROUP_OPTIONS = [
  "document",
  "email",
  "image",
  "table",
] as const;

export interface AnalyticParamDef {
  /** camelCase key, matches the backend parameter alias. */
  key: string;
  label: string;
  kind: AnalyticParamKind;
  defaultValue: number | string | boolean;
  min?: number;
  max?: number;
  step?: number;
  options?: readonly string[];
  /** Display names for `options`, when a value isn't readable as is. */
  optionLabels?: Readonly<Record<string, string>>;
  optional?: boolean;
  /** Plain-language explanation shown behind an info icon next to the label. */
  info?: string;
  /** `groups` only: send the picks as one comma-joined string (the CLI takes a comma list). */
  csv?: boolean;
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

/**
 * Form metadata for each analytic. Every param is a `cipher <command>` option with
 * the CLI's own default -- mirrors `cipher.schemas.dataset_request` (held to the
 * CLI by `test_request_params.py`).
 */
const minImageSide = (owner?: EnrichmentType): AnalyticParamDef => ({
  key: "minImageSide",
  label: "Min image side (px)",
  info: "Images whose shorter side is under this many pixels are skipped: spacers, tracking pixels, small icons. They stay in the dataset, they just aren't analysed.",
  kind: "number",
  min: 1,
  step: 1,
  defaultValue: 64,
  owner,
});

const llmConcurrency: AnalyticParamDef = {
  key: "concurrency",
  label: "LLM concurrency",
  info: "How many files are sent to the LLM at the same time. Higher is faster if the model server has room; 8 suits the local model.",
  kind: "number",
  min: 1,
  max: 64,
  step: 1,
  defaultValue: 8,
};

const textGroups = (defaultValue: string): AnalyticParamDef => ({
  key: "filetypeGroups",
  label: "Filetype groups",
  kind: "groups",
  options: [...TEXT_GROUP_OPTIONS],
  defaultValue,
  info: "Which kinds of file to read. Images only have text once OCR has run; spreadsheets (table) are usually better handled by Table extraction.",
});

export const ANALYTICS: readonly AnalyticDef[] = [
  {
    type: "archiveExtraction",
    label: "Archive extraction",
    description:
      "Unpack zip, tar (also .tar.gz, .xz, .zst), 7z, rar and iso archives into their files, flag encrypted ones, and decode compressed files such as report.csv.gz. Runs before everything that reads files.",
    params: [
      {
        key: "maxDepth",
        label: "Nesting depth",
        kind: "number",
        min: 0,
        max: 32,
        step: 1,
        info: "How many archives-inside-archives levels to open. Deeper ones are listed as skipped.",
        defaultValue: 5,
      },
      {
        key: "maxArchiveGib",
        label: "Largest archive to open (GiB)",
        kind: "number",
        min: 1,
        step: 1,
        optional: true,
        info: "Archives bigger than this are skipped. Empty: no limit for local files, 50 GiB for S3 (7z, rar and iso are copied locally before 7-Zip reads them).",
        defaultValue: "",
      },
      {
        key: "maxTotalGib",
        label: "Max per archive (GiB)",
        kind: "number",
        min: 1,
        step: 1,
        info: "Stop an archive that has written this much. Guards against zip bombs and full disks.",
        defaultValue: 20,
      },
      {
        key: "maxMemberGib",
        label: "Max per file (GiB)",
        kind: "number",
        min: 1,
        step: 1,
        info: "Stop an archive when one file inside it grows past this.",
        defaultValue: 8,
      },
      {
        key: "maxRatio",
        label: "Max compression ratio",
        kind: "number",
        min: 2,
        step: 10,
        info: "Stop a file that expands more than this many times its compressed size (past 64 MiB). Real files rarely pass 100; zip bombs reach millions.",
        defaultValue: 250,
      },
      {
        key: "maxEntries",
        label: "Max files per archive",
        kind: "number",
        min: 1,
        step: 1000,
        info: "Refuse an archive that lists more files than this.",
        defaultValue: 1000000,
      },
      {
        key: "minFreeGib",
        label: "Disk to keep free (GiB)",
        kind: "number",
        min: 0,
        step: 1,
        info: "Stop unpacking when the scratch disk has less free space than this.",
        defaultValue: 10,
      },
      {
        key: "sandbox",
        label: "7-Zip sandbox",
        kind: "select",
        options: ["bestEffort", "required", "off"],
        optionLabels: { bestEffort: "Best effort", required: "Required", off: "Off" },
        info: "7z, rar and iso are read by 7-Zip in a sandbox (no network, only the archive visible). Best effort uses what this machine allows; Required fails those archives where part of it can't apply; Off runs 7-Zip unconfined, for machines where the sandbox gets in its way (size limits still hold).",
        defaultValue: "bestEffort",
      },
    ],
  },
  {
    type: "textExtraction",
    label: "Text extraction",
    description:
      "Pull text out of emails and documents. Scanned pages are left to OCR.",
    dependsOn: ["archiveExtraction"],
    params: [
      {
        key: "chunker",
        label: "Chunker",
        kind: "select",
        options: ["clir", "kreuzberg"],
        info: "How document text is split into passages for search. clir splits by the embedding model's tokens; kreuzberg splits during extraction along the document's structure.",
        defaultValue: "clir",
      },
      {
        key: "chunkSize",
        label: "Chunk size (tokens)",
        kind: "number",
        min: 64,
        max: 4096,
        step: 32,
        info: "Passage length in tokens (roughly 3/4 of a word each). Keep equal to Text embedding's chunk size.",
        defaultValue: 256,
      },
      {
        key: "ocrBackend",
        label: "Inline OCR",
        kind: "select",
        options: ["none", "easyocr", "tesseract"],
        info: "OCR scanned PDF pages during extraction with a lighter CPU engine. Leave at none to let the OCR analytic read them with the stronger local model.",
        defaultValue: "none",
      },
      {
        // Images get their text from OCR, so they aren't a choice here.
        key: "filetypeGroups",
        label: "Filetype groups",
        kind: "groups",
        options: ["document", "email", "table"],
        info: "Which kinds of file to pull text from. Images get their text from OCR instead; add table to make spreadsheets searchable as text.",
        defaultValue: "document,email",
      },
      {
        key: "archives",
        label: "Unpack archives too",
        kind: "boolean",
        info: "Unpack archives first, and again for archives attached to emails (a zip can hold an email that attaches another zip).",
        defaultValue: true,
      },
      {
        key: "inlineImages",
        label: "Save images shown in email bodies",
        kind: "boolean",
        info: "Keep the images an email's body shows (logos, pasted screenshots) as files found in that email. They are never listed as its attachments.",
        defaultValue: true,
      },
    ],
  },
  {
    type: "ocr",
    label: "OCR",
    description:
      "Read scanned PDF pages and text-bearing images with a local OCR engine. Images pass a CLIP text gate first.",
    dependsOn: ["textExtraction"],
    params: [
      {
        key: "engine",
        label: "Engine",
        kind: "select",
        options: ["jina", "indra"],
        optionLabels: { jina: "jina-ocr-v1 (GPU)", indra: "Indra OCR (CPU)" },
        info: "jina-ocr-v1 runs on a GPU and is the stronger reader: poor scans, phone photos of paper, handwriting, complex tables. Indra OCR runs on CPU with no GPU or model server, fast on clean printed pages in many languages, weaker on handwriting, degraded scans and merged-cell tables. Unsure: try Indra on a sample and read a few files.",
        defaultValue: "jina",
      },
      {
        key: "clipThreshold",
        label: "Text gate threshold",
        kind: "number",
        min: 0,
        max: 1,
        step: 0.01,
        info: "Images are scored 0-1 by CLIP for looking like they contain text (screenshots, scans, receipts, signs) rather than photos. Only images at or above this are OCR'd: lower reads more, higher reads fewer. Uses Image embedding's vectors.",
        defaultValue: 0.5,
      },
      {
        key: "minChars",
        label: "Min text-layer chars / page",
        kind: "number",
        min: 0,
        step: 1,
        info: "Not every PDF page is OCR'd: only pages whose own text layer has fewer than this many characters, i.e. scanned or image-only pages. Pages that already have text are left alone.",
        defaultValue: 20,
      },
      {
        key: "allImages",
        label: "OCR every image",
        kind: "boolean",
        info: "Turn the text gate off and send every image to OCR, photos included. Much slower; use it when the gate misses text-bearing images.",
        defaultValue: false,
      },
      {
        key: "force",
        label: "OCR every PDF page",
        kind: "boolean",
        info: "Also OCR pages that already have a text layer, e.g. when that layer is garbled.",
        defaultValue: false,
      },
      {
        key: "figures",
        label: "Caption figures",
        kind: "boolean",
        info: "Also locate charts, photos and diagrams on each page and write a short caption for them. jina-ocr-v1 only; Indra OCR ignores it.",
        defaultValue: false,
      },
    ],
  },
  {
    type: "textEmbedding",
    label: "Text embedding",
    description: "Chunk and embed extracted text for semantic search.",
    dependsOn: ["textExtraction"],
    params: [
      {
        key: "chunkSize",
        label: "Chunk size (tokens)",
        kind: "number",
        min: 64,
        max: 4096,
        step: 32,
        info: "Passage length in tokens (roughly 3/4 of a word each). Keep equal to Text extraction's chunk size.",
        defaultValue: 256,
      },
      {
        key: "chunkOverlap",
        label: "Chunk overlap (tokens)",
        kind: "number",
        min: 0,
        max: 1024,
        step: 1,
        info: "Tokens repeated between neighbouring passages so a sentence split across a boundary is still found.",
        defaultValue: 0,
      },
      {
        key: "maxPages",
        label: "Max pages / doc",
        kind: "number",
        min: 1,
        step: 1,
        defaultValue: "",
        info: "Only embed the first N pages of each document so very long files don't flood search. Blank embeds every page.",
        optional: true,
      },
      textGroups("document,email,image"),
    ],
  },
  {
    type: "imageEmbedding",
    label: "Image embedding",
    description: "CLIP embeddings for image search and clustering.",
    dependsOn: ["archiveExtraction"],
    params: [
      minImageSide(),
      {
        key: "classify",
        label: "Score with tag heads",
        kind: "boolean",
        info: "While embedding, also predict image tags with the tag classifiers trained on your labels (Admin > Tag training).",
        defaultValue: false,
      },
    ],
  },
  {
    type: "exifLocation",
    label: "Photo locations",
    description: "Read GPS coordinates from photo EXIF onto the map. No model.",
    dependsOn: ["archiveExtraction"],
    params: [],
  },
  {
    type: "faceDetection",
    label: "Face recognition",
    description:
      "Detect faces in images and propose matches against known persons for review.",
    dependsOn: ["archiveExtraction"],
    emits: ["faceDetection", "faceMatching"],
    params: [
      minImageSide("faceDetection"),
      {
        key: "similarity",
        label: "Match threshold",
        kind: "number",
        min: 0,
        max: 1,
        step: 0.01,
        defaultValue: 0.61,
        info: "Cosine similarity 0-1 between two faces. At or above it a face is proposed as that person for review; nothing is assigned automatically. 0.61 is the app-wide face default.",
        owner: "faceMatching",
      },
      {
        key: "perFaceLimit",
        label: "Candidates per reference face",
        kind: "number",
        min: 1,
        step: 1,
        defaultValue: 500,
        info: "For each person's reference faces, how many of the most similar unassigned faces are checked against the threshold.",
        owner: "faceMatching",
      },
      {
        key: "verifiedOnly",
        label: "Match verified people only",
        kind: "boolean",
        defaultValue: false,
        info: "Only propose matches to people an analyst has verified, not to unnamed people created by face clustering.",
        owner: "faceMatching",
      },
    ],
  },
  {
    type: "faceClustering",
    label: "Face clustering",
    description:
      "Group unassigned faces into unnamed person identities. Small clusters stay unassigned.",
    dependsOn: ["faceDetection"],
    params: [
      {
        key: "similarity",
        label: "Cluster similarity",
        kind: "number",
        min: 0,
        max: 1,
        step: 0.01,
        info: "Cosine similarity 0-1 two faces need to be linked into the same cluster. 0.61 is the app-wide face default.",
        defaultValue: 0.61,
      },
      {
        key: "minImages",
        label: "Min images per person",
        kind: "number",
        min: 1,
        max: 1000,
        step: 1,
        info: "A cluster becomes a person only if its faces come from at least this many different images.",
        defaultValue: 3,
      },
      {
        key: "minFaces",
        label: "Min faces per person",
        kind: "number",
        min: 2,
        max: 1000,
        step: 1,
        info: "...and only if it holds at least this many faces.",
        defaultValue: 2,
      },
      {
        key: "k",
        label: "Neighbours per face",
        kind: "number",
        min: 2,
        max: 200,
        step: 1,
        info: "How many nearest faces each face is compared with when building clusters. Higher finds more links but is slower.",
        defaultValue: 20,
      },
      {
        key: "noMerge",
        label: "Never merge into existing",
        kind: "boolean",
        info: "Always create a new person for each cluster instead of adding it to a nearby person an earlier clustering run created.",
        defaultValue: false,
      },
    ],
  },
  {
    type: "contactExtraction",
    label: "Contact extraction",
    description:
      "Turn vCard contacts into names, emails and phone numbers for entity resolution.",
    dependsOn: ["archiveExtraction"],
    params: [],
  },
  {
    type: "selectorExtraction",
    label: "Selector extraction",
    description:
      "Find emails, phones, IPs, IBANs, handles and other identifiers in text and headers.",
    dependsOn: ["textExtraction"],
    params: [textGroups("document,email,image")],
  },
  {
    type: "entityExtraction",
    label: "Entity extraction",
    description:
      "Find people, organizations and places in text, with the relations between them.",
    dependsOn: ["textExtraction"],
    params: [
      {
        key: "extractor",
        label: "Engine",
        kind: "select",
        options: ["nerd", "gliner", "llm"],
        info: "nerd: fast GPU tagger, names only. gliner: also finds relations between names. llm: the local LLM, best quality but by far the slowest.",
        defaultValue: "nerd",
      },
      {
        key: "threshold",
        label: "Confidence threshold",
        kind: "number",
        min: 0,
        max: 1,
        step: 0.01,
        defaultValue: "",
        info: "The model scores each name it finds 0-1. Names below this are dropped: higher means fewer but more reliable names. Blank uses the engine's default (nerd 0.5, gliner 0.65); ignored by llm.",
        optional: true,
      },
      textGroups("document,email,image"),
    ],
  },
  {
    type: "relationshipExtraction",
    label: "Relationship extraction",
    description: "Build who-emailed-whom edges between email addresses.",
    dependsOn: ["entityExtraction", "selectorExtraction"],
    params: [],
  },
  {
    type: "eventExtraction",
    label: "Event extraction",
    description:
      "Calendar files into events; optionally an LLM read of email bodies, gated so only likely events reach it.",
    params: [
      {
        key: "llm",
        label: "Find events in email text",
        kind: "boolean",
        info: "Off: only calendar files (.ics) become events. On: the local LLM also reads email bodies for bookings, itineraries, meetings and memberships.",
        defaultValue: false,
      },
      {
        key: "docs",
        label: "Include documents",
        kind: "boolean",
        info: "With email text on, also read documents (PDF, Word) for events.",
        defaultValue: false,
      },
      {
        key: "gate",
        label: "Pre-filter with GLiNER",
        kind: "boolean",
        info: "Before the slow LLM read, a fast GLiNER model scores each email and only likely events go on. Spam and promotions are skipped either way.",
        defaultValue: true,
      },
      {
        key: "gateThreshold",
        label: "Pre-filter threshold",
        kind: "number",
        min: 0,
        max: 1,
        step: 0.01,
        info: "GLiNER scores each email 0-1 for 'a booking, itinerary or plan to meet' and for 'a membership', and keeps the higher. Emails at or above this go to the LLM. A small sample below it (5%) is read anyway to measure what the filter misses.",
        defaultValue: 0.4,
      },
      llmConcurrency,
    ],
  },
  {
    type: "signatureExtraction",
    label: "Email signature extraction",
    description:
      "Read the sign-off block at the bottom of emails: name, title, employer, department, phone. Not handwritten signatures.",
    dependsOn: ["textExtraction"],
    params: [
      {
        key: "includeBulk",
        label: "Include newsletters & notifications",
        kind: "boolean",
        info: "Gmail sorts mail into Promotions, Updates, Social and Forums. Those are skipped by default: their sign-offs are company boilerplate, not a person's signature.",
        defaultValue: false,
      },
      llmConcurrency,
    ],
  },
  {
    type: "tableExtraction",
    label: "Table extraction",
    description:
      "Propose a column mapping per spreadsheet layout. Rows reach the graph once a mapping is verified on Tables.",
    dependsOn: ["archiveExtraction"],
    params: [
      {
        key: "detectors",
        label: "Column detectors",
        kind: "groups",
        csv: true,
        options: ["header", "validators", "gliner", "nerd", "llm"],
        info: "How each column's meaning is guessed. header: from the column name. validators: from values that look like emails, phones or dates. gliner / nerd / llm: a model reads sample values; slower, but catches unlabeled name or place columns.",
        defaultValue: "header,validators",
      },
      {
        key: "region",
        label: "Phone region (ISO-2)",
        kind: "text",
        defaultValue: "",
        info: "Country code (e.g. US, GB) used to read phone numbers written without a + prefix.",
        optional: true,
      },
    ],
  },
  {
    type: "textSummarization",
    label: "Summaries",
    description:
      "A short AI summary of each file. One LLM call per file, so slow on large datasets; files can also be summarized one at a time from the viewer.",
    params: [
      textGroups("document,email,image,table"),
      {
        key: "language",
        label: "Language",
        kind: "text",
        info: "Language the summaries are written in, whatever language the file is in.",
        defaultValue: "English",
      },
      llmConcurrency,
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
  ANALYTIC_BY_TYPE[type]?.label ?? humanize(type);

const groupsSchema = z.array(z.enum(TEXT_GROUP_OPTIONS)).min(1);
const concurrencySchema = z.number().int().min(1).max(64);
const minImageSideSchema = z.number().int().min(1);
const noParams = z.object({});

/** Per-analytic parameter validation, keyed by enrichment type. */
export const paramSchemas: Record<EnrichmentType, z.ZodType> = {
  archiveExtraction: z.object({
    maxArchiveGib: z.number().positive().optional(),
    maxDepth: z.number().int().min(0).max(32),
    maxTotalGib: z.number().positive(),
    maxMemberGib: z.number().positive(),
    maxRatio: z.number().gt(1),
    maxEntries: z.number().int().min(1),
    minFreeGib: z.number().min(0),
    sandbox: z.enum(["bestEffort", "required", "off"]),
  }),
  textExtraction: z.object({
    chunker: z.enum(["kreuzberg", "clir"]),
    chunkSize: z.number().int().min(64).max(4096),
    ocrBackend: z.enum(["none", "easyocr", "tesseract"]),
    filetypeGroups: groupsSchema,
    archives: z.boolean(),
    inlineImages: z.boolean(),
  }),
  ocr: z.object({
    engine: z.enum(["jina", "indra"]),
    clipThreshold: z.number().min(0).max(1),
    minChars: z.number().int().min(0),
    allImages: z.boolean(),
    force: z.boolean(),
    figures: z.boolean(),
  }),
  textEmbedding: z.object({
    chunkSize: z.number().int().min(64).max(4096),
    chunkOverlap: z.number().int().min(0).max(1024),
    maxPages: z.number().int().min(1).optional(),
    filetypeGroups: groupsSchema,
  }),
  imageEmbedding: z.object({
    minImageSide: minImageSideSchema,
    classify: z.boolean(),
  }),
  exifLocation: noParams,
  faceDetection: z.object({ minImageSide: minImageSideSchema }),
  faceMatching: z.object({
    similarity: z.number().min(0).max(1),
    perFaceLimit: z.number().int().min(1),
    verifiedOnly: z.boolean(),
  }),
  faceClustering: z.object({
    similarity: z.number().min(0).max(1),
    minImages: z.number().int().min(1).max(1000),
    minFaces: z.number().int().min(2).max(1000),
    k: z.number().int().min(2).max(200),
    noMerge: z.boolean(),
  }),
  contactExtraction: noParams,
  selectorExtraction: z.object({ filetypeGroups: groupsSchema }),
  entityExtraction: z.object({
    extractor: z.enum(["llm", "gliner", "nerd"]),
    threshold: z.number().min(0).max(1).optional(),
    filetypeGroups: groupsSchema,
  }),
  relationshipExtraction: noParams,
  eventExtraction: z.object({
    llm: z.boolean(),
    docs: z.boolean(),
    gate: z.boolean(),
    gateThreshold: z.number().min(0).max(1),
    concurrency: concurrencySchema,
  }),
  signatureExtraction: z.object({
    includeBulk: z.boolean(),
    concurrency: concurrencySchema,
  }),
  tableExtraction: z.object({
    detectors: z
      .string()
      .regex(
        /^(header|validators|gliner|nerd|llm)(,(header|validators|gliner|nerd|llm))*$/,
        {
          message: "Comma list of: header, validators, gliner, nerd, llm",
        }
      ),
    region: z.string().length(2).optional(),
  }),
  textSummarization: z.object({
    filetypeGroups: groupsSchema,
    language: z.string().trim().min(1),
    concurrency: concurrencySchema,
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
/** `measured` from prior runs on this machine; `none` until an analytic has run here (nothing is guessed). */
export type EstimateConfidence = "measured" | "none";

export interface EnrichmentWorkload {
  enrichmentType: string;
  unit: string;
  unitCount: number;
  byteCount: number;
  estimable: boolean;
  note: string | null;
}

/** Mirrors backend `EnrichmentConfig`; `dependencies` maps a type to its direct hard prerequisites. */
export interface EnrichmentConfig {
  pipelineOrder: string[];
  dependencies: Record<string, string[]>;
  runnable: string[];
}

/** Every prerequisite of `type`, transitively, from the config's direct-dependency map. */
export function allPrerequisites(
  dependencies: Record<string, string[]>,
  type: string
): string[] {
  const out = new Set<string>();
  const visit = (t: string) => {
    for (const dep of dependencies[t] ?? []) {
      if (out.has(dep)) continue;
      out.add(dep);
      visit(dep);
    }
  };
  visit(type);
  return [...out];
}

export interface EnrichmentEstimate {
  enrichmentType: string;
  /** Device class the analytic runs on; `na` = no local model (CPU parsing or a served LLM). */
  device: RunDevice;
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
  accelerator: RunDevice;
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

/** Sequential total of the timed estimates, plus how many analytics with work left have no timing yet. */
export function sumEstimates(items: EnrichmentEstimate[]): string {
  const seconds = items.reduce((sum, it) => sum + (it.estimateSeconds ?? 0), 0);
  const untimed = items.filter(
    (it) =>
      it.estimateSeconds == null &&
      it.eligible.estimable &&
      it.eligible.unitCount > 0 &&
      it.progress < 0.999
  ).length;
  if (!untimed) return formatDuration(seconds);
  const note = `${untimed} not yet timed`;
  return seconds > 0 ? `${formatDuration(seconds)} + ${note}` : note;
}

/* -------------------------------------------------------------------------- */
/*  Enrichment requests (mirrors backend `EnrichmentRequest`)                 */
/* -------------------------------------------------------------------------- */

export const enrichmentRequestSchema = z.object({
  datasetId: z.string().min(1),
  analytics: z
    .array(
      z.object({
        enrichmentType: z.string(),
        parameters: z.record(z.string(), z.unknown()),
      })
    )
    .min(1, "Select at least one analytic"),
  note: z
    .string()
    .trim()
    .max(5000, "Keep the note under 5000 characters")
    .optional(),
});

export type EnrichmentRequestInput = z.infer<typeof enrichmentRequestSchema>;

export interface EnrichmentRequestResult {
  title: string;
  /** Issue markdown -- copy it into an issue when GitHub isn't configured. */
  body: string;
  issueNumber: number | null;
  issueUrl: string | null;
}
