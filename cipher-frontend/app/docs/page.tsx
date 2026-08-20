"use client";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  ArrowDown,
  ArrowRight,
  Box,
  Braces,
  ChevronRight,
  Code2,
  Database,
  FileText,
  HelpCircle,
  IdCard,
  ImageIcon,
  Mail,
  MessagesSquare,
  Search,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";

type ServiceLinks = { model?: string; code?: string };

const PIPELINE = [
  {
    num: "01",
    title: "Detect",
    services: ["filetyper"],
    ml: false,
    description:
      "Every incoming file is hashed (MD5 + SHA-256) and typed before anything else touches it -- filetype_group, filetype, and MIME type, resolved by Magika's model with custom heuristics layered on top where Magika lacks specificity.",
  },
  {
    num: "02",
    title: "Extract",
    services: ["pyxberg", "pyparse"],
    ml: false,
    description:
      "The extractor is chosen per filetype group -- Xberg (Rust) handles general documents and OCR by default; pyparse takes email, contact, and legacy Office formats. Output is normalized to markdown or plain text, with chunk spans preserved where the extractor produces its own.",
  },
  {
    num: "03",
    title: "Embed & enrich",
    services: ["clir", "setfitcv", "face"],
    ml: true,
    description:
      "Text gets multilingual embeddings, images get CLIP embeddings, faces get detected and embedded. Each enrichment is tracked as its own job -- type, status, retry count -- against the entity it belongs to, so a failed embedding doesn't block everything else.",
  },
  {
    num: "04",
    title: "Index",
    services: ["postgres · pgvector", "elasticsearch"],
    ml: false,
    description:
      "Structured records and vectors land in Postgres; full-text and hybrid search live in Elasticsearch. Both are kept in sync per dataset so search can blend keyword and semantic ranking.",
  },
  {
    num: "05",
    title: "Serve",
    services: ["cipher-serve"],
    ml: false,
    description:
      "The FastAPI backend exposes typed REST endpoints per entity -- files, emails, images, messages, persons, faces, comments -- plus search and a chat endpoint with citations back into the underlying records.",
  },
  {
    num: "06",
    title: "Triage",
    services: ["next.js frontend"],
    ml: false,
    description:
      "Analysts browse, filter, annotate, and search the dataset, or ask questions of it directly through chat. AI/ML-derived surfaces are visually marked so a reviewer always knows what's a model's read versus ground truth.",
  },
];

const FILETYPES: {
  name: string;
  icon: ReactNode;
  description: string;
  extensions: string[];
  handler: string;
}[] = [
  {
    name: "Documents",
    icon: <FileText size={16} />,
    description: "Office files, PDFs, and plain text -- extracted, OCR'd where needed, chunked, and embedded for semantic search.",
    extensions: [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".rtf", ".html"],
    handler: "pyxberg → clir",
  },
  {
    name: "Emails",
    icon: <Mail size={16} />,
    description: "Full message parsing -- headers, participants, body, attachments split back out as child files linked to the parent.",
    extensions: [".eml", ".msg"],
    handler: "pyparse → clir",
  },
  {
    name: "Contacts",
    icon: <IdCard size={16} />,
    description: "vCards parsed into structured contact records -- names, numbers, addresses -- linkable back to the file or email they came from.",
    extensions: [".vcf"],
    handler: "pyparse",
  },
  {
    name: "Images",
    icon: <ImageIcon size={16} />,
    description: "Embedded for visual + text-to-image similarity search, and scanned for faces, which are clustered into person identities across the dataset.",
    extensions: [".jpg", ".png", ".gif", ".tiff", ".webp"],
    handler: "setfitcv + face",
  },
  {
    name: "Messages & conversations",
    icon: <MessagesSquare size={16} />,
    description: "Chat and SMS exports, ingested as structured message + conversation-chunk records rather than raw files, with optional translation before embedding.",
    extensions: ["chat export", "sms/mms"],
    handler: "pyparse → clir",
  },
  {
    name: "Unclassified",
    icon: <HelpCircle size={16} />,
    description: "Anything Magika and the heuristics can't confidently bucket still gets hashed, sized, and made browsable -- nothing silently drops out of the dataset.",
    extensions: ["other / binary"],
    handler: "filetyper (fallback)",
  },
];

const ANALYTICS: {
  name: string;
  role: "AI/ML" | "Parser";
  description: string;
  tech: string;
  links: ServiceLinks;
}[] = [
  {
    name: "filetyper",
    role: "AI/ML",
    description: "Detects file type by combining Python's filetype heuristics with Google's Magika where heuristics lack specificity -- the first stop for every ingested file.",
    tech: "Magika (AI-based file identification)",
    links: { model: "#", code: "#" },
  },
  {
    name: "pyxberg",
    role: "AI/ML",
    description: "Rust-based text extraction and OCR (formerly Kreuzberg). Default extractor for the document filetype group -- normalizes to markdown or plain text with chunk spans preserved.",
    tech: "Kreuzberg extraction + OCR",
    links: { model: "#", code: "#" },
  },
  {
    name: "pyparse",
    role: "Parser",
    description: "Structured parsing for email, contacts, and legacy Microsoft Office formats -- Aspose-backed where a faster native parser beats generic conversion.",
    tech: ".eml · .msg · .vcf · legacy .doc/.ppt",
    links: { code: "#" },
  },
  {
    name: "clir",
    role: "AI/ML",
    description: "Multilingual text embedding for document, email, and message chunks -- the backbone of semantic and hybrid search across languages.",
    tech: "Jina multilingual embeddings",
    links: { model: "#", code: "#" },
  },
  {
    name: "setfitcv",
    role: "AI/ML",
    description: "Batch image embedding via CLIP -- powers image-to-image similarity and text-to-image search over everything tagged image.",
    tech: "CLIP (image/text joint embedding)",
    links: { model: "#", code: "#" },
  },
  {
    name: "face",
    role: "AI/ML",
    description: "Face detection and embedding across every image in a dataset, feeding person clustering and cross-file identity matching.",
    tech: "InsightFace",
    links: { model: "#", code: "#" },
  },
];

type Field = { key: string; type: string; ml?: boolean };
const SCHEMAS: { name: string; vector: boolean; extends?: string; fields: Field[] }[] = [
  {
    name: "Dataset",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "name", type: "str" },
      { key: "description", type: "str | null" },
      { key: "date_created", type: "datetime" },
      { key: "date_last_updated", type: "datetime" },
    ],
  },
  {
    name: "File",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "dataset_id", type: "str" },
      { key: "filename", type: "str" },
      { key: "filetype_group", type: "str" },
      { key: "filetype", type: "str" },
      { key: "mime_type", type: "str" },
      { key: "md5", type: "str" },
      { key: "sha256", type: "str" },
      { key: "size", type: "int" },
      { key: "parent_id", type: "str | null" },
    ],
  },
  {
    name: "TextChunk",
    vector: true,
    extends: "extended by DocumentTextChunk, EmailTextChunk",
    fields: [
      { key: "id", type: "str" },
      { key: "dataset_id", type: "str" },
      { key: "file_id", type: "str" },
      { key: "chunk_index", type: "int" },
      { key: "start_offset", type: "int" },
      { key: "end_offset", type: "int" },
      { key: "text", type: "str" },
      { key: "embedding", type: "float[]", ml: true },
      { key: "tags", type: "str[]" },
      { key: "keywords", type: "str[]" },
    ],
  },
  {
    name: "Image",
    vector: true,
    fields: [
      { key: "id", type: "str" },
      { key: "width", type: "int" },
      { key: "height", type: "int" },
      { key: "camera_make", type: "str | null" },
      { key: "date_taken", type: "datetime | null" },
      { key: "tags", type: "str[]" },
      { key: "embedding", type: "float[512]", ml: true },
      { key: "embedding_model", type: "str | null", ml: true },
    ],
  },
  {
    name: "Contact",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "full_name", type: "str | null" },
      { key: "emails", type: "str[]" },
      { key: "phone_numbers", type: "PhoneNumber[]" },
      { key: "organization", type: "str | null" },
      { key: "file_id", type: "str | null" },
      { key: "device_id", type: "str | null" },
    ],
  },
  {
    name: "Message",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "message_id", type: "str" },
      { key: "sender", type: "str" },
      { key: "recipient", type: "str" },
      { key: "date_sent", type: "datetime | null" },
      { key: "text", type: "str | null" },
      { key: "translation", type: "str | null", ml: true },
      { key: "conversation_id", type: "str" },
      { key: "message_status", type: "MessageStatus" },
    ],
  },
  {
    name: "ConversationChunk",
    vector: true,
    fields: [
      { key: "id", type: "str" },
      { key: "conversation_id", type: "str" },
      { key: "date", type: "datetime | null" },
      { key: "messages", type: "MessageBase[]" },
      { key: "embedding", type: "TextEmbedding", ml: true },
    ],
  },
  {
    name: "Person",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "name", type: "str | null" },
      { key: "aliases", type: "str[]" },
      { key: "tags", type: "str[]" },
      { key: "is_verified", type: "bool" },
      { key: "source", type: '"manual" | "face_clustering"' },
    ],
  },
  {
    name: "Face",
    vector: true,
    fields: [
      { key: "id", type: "str" },
      { key: "image_id", type: "str" },
      { key: "bounding_box", type: "FaceBoundingBox" },
      { key: "landmarks", type: "FaceLandmark[]" },
      { key: "detection_confidence", type: "float | null", ml: true },
      { key: "quality_score", type: "float | null" },
      { key: "embedding", type: "FaceEmbedding", ml: true },
      { key: "embedding_model", type: "str | null", ml: true },
    ],
  },
  {
    name: "FaceMatch",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "face_id", type: "str" },
      { key: "person_id", type: "str" },
      { key: "similarity_score", type: "float", ml: true },
      { key: "match_method", type: '"automatic_similarity" | "automatic_clustering" | "manual"' },
      { key: "status", type: '"pending" | "confirmed" | "rejected"' },
    ],
  },
  {
    name: "Device",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "name", type: "str | null" },
      { key: "manufacturer", type: "str | null" },
      { key: "model", type: "str | null" },
      { key: "os_type", type: "str | null" },
      { key: "imeis", type: "str[]" },
      { key: "date_first_seen", type: "datetime | null" },
      { key: "date_last_seen", type: "datetime | null" },
    ],
  },
  {
    name: "Comment",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "content", type: "str" },
      { key: "commentable_type", type: '"dataset" | "image" | "person" | "file"' },
      { key: "commentable_id", type: "str" },
      { key: "user_id", type: "str" },
    ],
  },
  {
    name: "Enrichment",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "enrichable_type", type: '"file" | "message" | "contact" | "image" | "face"' },
      { key: "enrichable_id", type: "str" },
      { key: "enrichment_type", type: "EnrichmentType", ml: true },
      { key: "status", type: '"pending" | "processing" | "completed" | "failed" | "skipped"' },
      { key: "retry_count", type: "int" },
    ],
  },
  {
    name: "User",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "name", type: "str" },
      { key: "email", type: "str" },
      { key: "date_created", type: "datetime" },
    ],
  },
];

function SectionEyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
      {children}
    </span>
  );
}

function ServiceLink({
  href,
  label,
  icon,
}: {
  href: string;
  label: string;
  icon: ReactNode;
}) {
  return (
    <a
      href={href}
      title={`${label} -- placeholder link, wire up when pinned down`}
      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 px-2 py-1 text-[11px] font-mono text-slate-400 transition-colors hover:border-indigo-400/50 hover:bg-indigo-400/10 hover:text-indigo-300"
    >
      {icon}
      {label}
    </a>
  );
}

const FLOW_VARIANTS = {
  default: { border: "border-white/10 bg-white/[0.02]", text: "text-slate-200" },
  ml: { border: "border-annotation/50 bg-annotation/5", text: "text-annotation" },
  vector: { border: "border-indigo-400/50 bg-indigo-400/5", text: "text-indigo-300" },
  search: { border: "border-cyan-400/50 bg-cyan-400/5", text: "text-cyan-300" },
} as const;

function FlowNode({
  title,
  subtitle,
  variant = "default",
}: {
  title: string;
  subtitle: string;
  variant?: keyof typeof FLOW_VARIANTS;
}) {
  const styles = FLOW_VARIANTS[variant];
  return (
    <div
      className={cn(
        "flex min-w-32 flex-col items-center gap-0.5 rounded-lg border px-3 py-2.5 text-center",
        styles.border
      )}
    >
      <span className={cn("text-xs font-semibold", styles.text)}>{title}</span>
      <span className="font-mono text-[10px] text-slate-500">{subtitle}</span>
    </div>
  );
}

export default function DocsPage() {
  return (
    <div className="max-w-350 mx-auto px-6 relative pb-24">
      <PageHeader eyebrow="Documentation" value="Platform overview" icon={<Braces size={14} className="text-indigo-400/80" />} />

      {/* Masthead */}
      <div className="pt-4 pb-10">
        <h1 className="text-4xl font-bold tracking-tight text-slate-100 sm:text-5xl">Cipher</h1>
        <p className="mt-3 max-w-2xl text-base text-slate-400">
          A triage platform for unknown data. Point it at a pile of files, mailboxes, images, and message exports --
          it types everything against defined schemas, runs AI/ML enrichment over it, and makes the result searchable.
        </p>
        <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-slate-500">
          <span>
            API <b className="font-semibold text-slate-300">FastAPI · cipher-serve</b>
          </span>
          <span>
            UI <b className="font-semibold text-slate-300">Next.js</b>
          </span>
          <span>
            STORES <b className="font-semibold text-slate-300">PostgreSQL/pgvector · Elasticsearch</b>
          </span>
        </div>
      </div>

      <Separator className="bg-white/10" />

      {/* Pipeline */}
      <section className="py-10">
        <div className="mb-6 flex items-center gap-2.5">
          <Workflow size={16} className="text-indigo-400" />
          <SectionEyebrow>How a file becomes a record</SectionEyebrow>
        </div>
        <div className="flex flex-col">
          {PIPELINE.map((stage, i) => (
            <div
              key={stage.num}
              className={cn(
                "grid grid-cols-[3rem_1fr] gap-5 border-t border-white/10 py-5 pl-3.5 border-l-2",
                i === 0 && "border-t-0",
                stage.ml ? "border-l-annotation/50" : "border-l-transparent"
              )}
            >
              <div className="pt-0.5 font-mono text-xl font-semibold text-white/15">{stage.num}</div>
              <div>
                <h3 className="mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-200">
                  {stage.title}
                  {stage.services.map((s) => (
                    <Badge key={s} variant="outline" className="font-mono text-[10px] font-normal text-slate-400">
                      {s}
                    </Badge>
                  ))}
                </h3>
                <p className="max-w-2xl text-sm text-slate-400">{stage.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <Separator className="bg-white/10" />

      {/* File types */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <FileText size={16} className="text-indigo-400" />
          <SectionEyebrow>What it ingests</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-slate-500">
          Six broad categories, each with its own parser and its own downstream enrichment. Extensions shown are
          representative, not exhaustive.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {FILETYPES.map((ft) => (
            <Card key={ft.name} className="ring-white/10">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-slate-200">
                  <span className="text-indigo-400">{ft.icon}</span>
                  {ft.name}
                </CardTitle>
                <CardDescription>{ft.description}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-1.5">
                  {ft.extensions.map((ext) => (
                    <span
                      key={ext}
                      className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
                    >
                      {ext}
                    </span>
                  ))}
                </div>
                <div className="border-t border-dashed border-white/10 pt-2.5 font-mono text-[11px] text-slate-500">
                  handled by <span className="font-semibold text-indigo-400">{ft.handler}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator className="bg-white/10" />

      {/* Analytics services */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Box size={16} className="text-indigo-400" />
          <SectionEyebrow>Analytics services</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-slate-500">
          Each service is independently deployable and does exactly one job. Model / paper / code links are
          placeholders -- wire them up per service as they&apos;re pinned down.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {ANALYTICS.map((svc) => (
            <Card key={svc.name} className="ring-white/10">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="font-mono text-slate-100">{svc.name}</CardTitle>
                  <Badge
                    className={cn(
                      "font-mono text-[10px] uppercase tracking-wide",
                      svc.role === "AI/ML"
                        ? "border-annotation/40 bg-annotation/10 text-annotation"
                        : "border-white/15 bg-white/5 text-slate-400"
                    )}
                    variant="outline"
                  >
                    {svc.role}
                  </Badge>
                </div>
                <CardDescription>{svc.description}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-2 font-mono text-[11px] text-slate-400">
                  {svc.tech}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {svc.links.model && (
                    <ServiceLink href={svc.links.model} label="Model" icon={<Box size={12} />} />
                  )}
                  {svc.links.code && (
                    <ServiceLink href={svc.links.code} label="Code" icon={<Code2 size={12} />} />
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator className="bg-white/10" />

      {/* Architecture */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Database size={16} className="text-indigo-400" />
          <SectionEyebrow>Architecture</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-slate-500">
          One request path for ingestion, one for search -- both converge on the same two datastores.
        </p>

        <Card className="ring-white/10">
          <CardContent className="flex flex-col items-center gap-4 overflow-x-auto py-6">
            <div className="flex min-w-max items-center gap-2">
              <FlowNode title="Raw data" subtitle="unknown files" />
              <ArrowRight size={16} className="shrink-0 text-slate-600" />
              <FlowNode title="filetyper" subtitle="type + hash" />
              <ArrowRight size={16} className="shrink-0 text-slate-600" />
              <FlowNode title="pyxberg / pyparse" subtitle="text + OCR" />
              <ArrowRight size={16} className="shrink-0 text-slate-600" />
              <FlowNode title="clir · setfitcv · face" subtitle="embeddings" variant="ml" />
              <ArrowRight size={16} className="shrink-0 text-slate-600" />
              <div className="flex flex-col gap-1.5">
                <FlowNode title="Postgres" subtitle="+ pgvector" variant="vector" />
                <FlowNode title="Elasticsearch" subtitle="text + hybrid" variant="search" />
              </div>
              <ArrowRight size={16} className="shrink-0 text-slate-600" />
              {/* Stacked in the same column as the frontend node below, so the
                  "serves" relationship reads directly instead of via a
                  down-arrow centered under the whole row. */}
              <div className="flex flex-col items-center gap-1.5">
                <FlowNode title="FastAPI" subtitle="cipher-serve" />
                <ArrowDown size={14} className="text-slate-600" />
                <FlowNode title="Next.js frontend" subtitle="browse · search · chat" />
              </div>
            </div>

            <p className="max-w-md text-center font-mono text-[11px] text-slate-600">
              chat answers cite back into indexed records
            </p>
          </CardContent>
        </Card>

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 font-mono text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-annotation" /> AI/ML enrichment
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-indigo-400" /> relational + vector
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-cyan-400" /> search index
          </span>
        </div>
      </section>

      <Separator className="bg-white/10" />

      {/* Schemas */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Braces size={16} className="text-indigo-400" />
          <SectionEyebrow>Schemas</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-slate-500">
          Every entity in Cipher is a typed Pydantic model shared across every service -- this is the shape a
          dataset decomposes into. Expand a schema to see its field shape; the{" "}
          <Badge variant="outline" className="border-annotation/40 bg-annotation/10 text-[10px] text-annotation">
            vector
          </Badge>{" "}
          tag marks anything carrying an embedding.
        </p>

        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
          {SCHEMAS.map((schema) => (
            <Collapsible key={schema.name}>
              <div className="rounded-lg border border-white/10 bg-white/[0.02]">
                <CollapsibleTrigger className="group/trigger flex w-full items-center gap-2.5 px-3.5 py-3 text-left">
                  <Braces
                    size={15}
                    className={cn("shrink-0", schema.vector ? "text-annotation" : "text-indigo-400")}
                  />
                  <span className="flex-1 font-mono text-[13px] text-slate-200">{schema.name}</span>
                  {schema.vector && (
                    <Badge
                      variant="outline"
                      className="border-annotation/40 bg-annotation/10 text-[10px] uppercase tracking-wide text-annotation"
                    >
                      vector
                    </Badge>
                  )}
                  <ChevronRight
                    size={13}
                    className="shrink-0 text-slate-600 transition-transform group-data-[state=open]/trigger:rotate-90"
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-none">
                  <pre className="overflow-x-auto border-t border-dashed border-white/10 px-3.5 py-3 pl-9 font-mono text-[12px] leading-relaxed text-slate-500">
                    {schema.fields.map((f) => (
                      <div key={f.key}>
                        <span className="text-slate-300">{f.key}</span>:{" "}
                        <span className={f.ml ? "text-annotation" : "text-cyan-400"}>{f.type}</span>
                      </div>
                    ))}
                    {schema.extends && <div className="mt-1 text-slate-600">&#8627; {schema.extends}</div>}
                  </pre>
                </CollapsibleContent>
              </div>
            </Collapsible>
          ))}
        </div>
      </section>

      <Separator className="bg-white/10" />

      <div className="flex flex-wrap items-center justify-between gap-2 py-6 font-mono text-[11px] text-slate-600">
        <span>cipher/ -- UV workspace monorepo</span>
        <span className="inline-flex items-center gap-1.5">
          <Search size={12} />
          fill in service links above as they&apos;re pinned down
        </span>
      </div>
    </div>
  );
}
