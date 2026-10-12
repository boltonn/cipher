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
  CalendarDays,
  ChevronRight,
  Code2,
  Database,
  FileText,
  HelpCircle,
  IdCard,
  ImageIcon,
  Mail,
  Share2,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

type ServiceLinks = { model?: string; code?: string };

const PIPELINE = [
  {
    num: "01",
    title: "Stage",
    services: ["filetyper"],
    ml: true,
    description:
      "Every file is hashed (MD5 + SHA-256) and typed before anything else touches it -- filetype_group, filetype, and MIME type, from Magika's model with heuristics layered on top. A dataset is staged once its files are loaded; that inventory is what every time estimate is sized against.",
  },
  {
    num: "02",
    title: "Extract",
    services: ["pyxberg", "pyparse", "pyvllm"],
    ml: true,
    description:
      "The extractor is chosen per filetype group -- pyxberg (Kreuzberg) for documents, pyparse for email, contacts, and calendar files (email attachments become child files). Image-based PDF pages and text-bearing images are then read by the OCR model (jina-ocr-v1) that pyvllm serves.",
  },
  {
    num: "03",
    title: "Embed",
    services: ["clir", "setfitcv", "face"],
    ml: true,
    description:
      "Extracted text is chunked and embedded for multilingual search, images get CLIP embeddings, and faces are detected, embedded, matched to known persons, and clustered into new ones. Each enrichment is tracked per file (status, retries), so one failure never blocks the rest.",
  },
  {
    num: "04",
    title: "Find mentions",
    services: ["pyselectors", "pygliner", "nerd", "pyprompt"],
    ml: true,
    description:
      "Mentions are pulled from text: selectors (phones, emails, IBANs, …) deterministically; person, organization, and location names with GLiNER, a fine-tuned NER model, or an LLM; events from .ics files or email bodies; contacts from vCards; and each sender's email signature -- employer, division, department, title, and work contact details -- read by the LLM in any language.",
  },
  {
    num: "05",
    title: "Resolve",
    services: ["cipher-names", "resolve-entities"],
    ml: false,
    description:
      "One call (resolve-entities) runs the whole stage. Mentions are grouped by name and scored against existing entities (Fellegi-Sunter, explainable per signal): confident matches attach, uncertain ones go to review, unmatched ones become auto-created entities. Places resolve against an offline gazetteer. Every spelling of a name is one unit (Adaire, Adaire's, Adaire (no reply), even tagged person in one email and organization in another): auto-created copies fold, and the unit gets one entity, not one per spelling; possible duplicates wait on the Verify tab. Email headers become directed emailed edges; email-signature and email-domain affiliations become reviewable suggestions (the Entities page's Email signatures tab, and each organization's page).",
  },
  {
    num: "06",
    title: "Store & serve",
    services: ["postgres", "cipher-serve"],
    ml: false,
    description:
      "One Postgres database holds records, chunks, vectors (pgvector), BM25 keyword search (pg_search), and geometry (PostGIS), so keyword, semantic, entity, and graph filters run as one query. The FastAPI backend serves it all, plus a chat agent that cites back into the records.",
  },
  {
    num: "07",
    title: "Triage",
    services: ["next.js frontend"],
    ml: false,
    description:
      "Analysts browse datasets and files, search, review entities, faces, events, and locations, browse organization charts, walk the graph, and ask questions in chat. AI/ML-derived surfaces are marked amber so a reviewer always knows what's a model's read versus ground truth.",
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
    description:
      "Office files, PDFs, and plain text -- extracted, OCR'd where pages are scanned, chunked, and embedded for keyword and semantic search.",
    extensions: [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".rtf", ".html"],
    handler: "pyxberg (+ pyvllm OCR) → clir",
  },
  {
    name: "Emails",
    icon: <Mail size={16} />,
    description:
      "Headers, participants, body, and attachments (split back out as child files). Headers feed selectors and directed emailed edges between addresses; the sender's email signature feeds who they work for, in which unit, and their work phone / address.",
    extensions: [".eml", ".msg"],
    handler: "pyparse → clir",
  },
  {
    name: "Contacts",
    icon: <IdCard size={16} />,
    description:
      "vCards parsed into contact records, then into name and selector mentions (with member_of for organizations) for entity resolution.",
    extensions: [".vcf"],
    handler: "pyparse → mentions",
  },
  {
    name: "Calendars",
    icon: <CalendarDays size={16} />,
    description:
      "Calendar entries become events with participants and places, linked to entities and locations once resolved.",
    extensions: [".ics"],
    handler: "pyparse → events",
  },
  {
    name: "Images",
    icon: <ImageIcon size={16} />,
    description:
      "Embedded for image-to-image and text-to-image search, scanned for faces (matched or clustered into persons), and mapped from EXIF GPS.",
    extensions: [".jpg", ".png", ".gif", ".tiff", ".webp", ".heic"],
    handler: "setfitcv + face",
  },
  {
    name: "Unclassified",
    icon: <HelpCircle size={16} />,
    description:
      "Anything Magika and the heuristics can't confidently bucket still gets hashed, sized, and made browsable -- nothing silently drops out of the dataset.",
    extensions: ["other / binary"],
    handler: "filetyper (fallback)",
  },
];

const ANALYTICS: {
  name: string;
  role: "AI/ML" | "Parser";
  description: string;
  tech: string;
  /** `cipher` CLI commands that run it -- see docs/running-analytics.md. */
  commands: string[];
  links: ServiceLinks;
}[] = [
  {
    name: "filetyper",
    role: "AI/ML",
    description:
      "Types every file by combining filetype heuristics with Google's Magika where heuristics lack specificity -- the first stop for every ingested file.",
    tech: "Magika (AI-based file identification)",
    commands: ["load-files"],
    links: { model: "#", code: "#" },
  },
  {
    name: "pyxberg",
    role: "AI/ML",
    description:
      "Rust-based document text extraction. Records which PDF pages are image-based so the OCR step reads just those; inline EasyOCR / Tesseract is only an offline fallback (--ocr-backend) when no GPU is available.",
    tech: "Kreuzberg (+ optional EasyOCR / Tesseract)",
    commands: ["extract-text"],
    links: { model: "#", code: "#" },
  },
  {
    name: "pyparse",
    role: "Parser",
    description:
      "Structured parsing for email, contacts, calendars, and legacy Microsoft Office formats.",
    tech: ".eml · .msg · .vcf · .ics · legacy .doc/.ppt",
    commands: ["extract-text", "extract-contact-entities", "extract-events"],
    links: { code: "#" },
  },
  {
    name: "pyvllm",
    role: "AI/ML",
    description:
      "Every local model on one vLLM install: the LLM behind chat and pyprompt, and the OCR model that reads image-based PDF pages and text-bearing images (started by the ocr step). OCR weights are non-commercial (CC BY-NC).",
    tech: "vLLM · Qwen3.8-27B · jina-ocr-v1",
    commands: ["ocr"],
    links: { model: "#", code: "#" },
  },
  {
    name: "clir",
    role: "AI/ML",
    description:
      "Multilingual text embedding for document and email chunks -- the semantic half of hybrid search, across languages.",
    tech: "Jina multilingual embeddings",
    commands: ["embed-text"],
    links: { model: "#", code: "#" },
  },
  {
    name: "setfitcv",
    role: "AI/ML",
    description:
      "CLIP image embedding -- powers image-to-image and text-to-image search, reads EXIF GPS into locations, and filters which images are worth OCR. Tag heads: train one small classifier per analyst tag on the stored embeddings, then score every image with it.",
    tech: "CLIP (image/text joint embedding)",
    commands: [
      "embed-images",
      "extract-locations",
      "train-image-heads",
      "score-image-heads",
    ],
    links: { model: "#", code: "#" },
  },
  {
    name: "face",
    role: "AI/ML",
    description:
      "Face detection and embedding across every image, then matching to known persons and clustering the rest into new ones. Faces marked “not a face” auto-reject their look-alikes; people sharing a photo get appears_in_photo_with edges.",
    tech: "InsightFace",
    commands: [
      "detect-faces",
      "match-faces",
      "cluster-faces",
      "reject-similar-faces",
      "link-face-cooccurrence",
    ],
    links: { model: "#", code: "#" },
  },
  {
    name: "pyselectors",
    role: "Parser",
    description:
      "Deterministic extraction of strong identifiers -- phone, email, IBAN, passport, IMEI, crypto address, … -- normalized, validated, and context-scored. About 1 ms per document.",
    tech: "Pattern packs, no ML",
    commands: ["extract-selectors"],
    links: { code: "#" },
  },
  {
    name: "pygliner",
    role: "AI/ML",
    description:
      "Zero-shot, multilingual entity and relation extraction; labels come from the ontology at inference time.",
    tech: "GLiNER2.5",
    commands: ["extract-entities --extractor gliner"],
    links: { model: "#", code: "#" },
  },
  {
    name: "nerd",
    role: "AI/ML",
    description:
      "Supervised multilingual named-entity recognition -- fast batched GPU inference for person, organization, and location names.",
    tech: "Fine-tuned XLM-RoBERTa token classification",
    commands: ["extract-entities --extractor nerd"],
    links: { model: "#", code: "#" },
  },
  {
    name: "pyprompt",
    role: "AI/ML",
    description:
      "LLM prompt runner for structured extraction -- entities and events (plus memberships: clubs, gyms, accounts the recipient belongs to) from email bodies in one call per email. Slowest, most flexible. Also reads email signatures (below).",
    tech: "OpenAI-compatible LLM + prompt packs",
    commands: [
      "extract-llm",
      "extract-entities --extractor llm",
      "extract-events --llm",
    ],
    links: { code: "#" },
  },
  {
    name: "email signatures",
    role: "AI/ML",
    description:
      "Who each sender works for, in which unit, and how to reach them. First pass (rules): bulk mail is skipped, and the last lines the sender wrote are only sent on when someone may be signing off (a farewell phrase, the sender's name, an NER person) and there is something to learn (an organization, phone, website or other email address) -- about 5% of a mailbox. The multilingual word lists are one file (signature_cues.py). The LLM then decides whether it's really an email signature and copies out company → division → department, title, phone, email, website and address; code checks every value is verbatim, the signer is the sender, and it isn't a brand. Each address's city comes from the gazetteer (never guessed), and phones keep a country only when the number states one. A sender's known email signature is reused without another call. Review on the Entities page's Email signatures tab: fix labels in the text and accept, correct, reject or add relationships. Full walkthrough: docs/signatures.md.",
    tech: "Gate + pyprompt signature pack (local LLM)",
    commands: ["extract-signatures", "resolve-entities"],
    links: { code: "#" },
  },
  {
    name: "cipher-names",
    role: "Parser",
    description:
      "Name parsing, transliteration, nicknames, and blocking keys behind entity resolution: candidates are scored Fellegi-Sunter style with a per-signal explanation, so every match can be reviewed.",
    tech: "Rule-based name matching, no ML",
    commands: ["resolve-entities"],
    links: { code: "#" },
  },
  {
    name: "cipher-places",
    role: "Parser",
    description:
      "Offline gazetteer: place mentions resolve to shared country / state / city / region entities using the text around each mention; ambiguous names stay unresolved.",
    tech: "Offline gazetteer index (cipher-places-build)",
    commands: ["resolve-locations"],
    links: { code: "#" },
  },
];

type Field = { key: string; type: string; ml?: boolean };
const SCHEMAS: {
  name: string;
  vector: boolean;
  extends?: string;
  fields: Field[];
}[] = [
  {
    name: "Dataset",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "name", type: "str" },
      { key: "description", type: "str | null" },
      { key: "date_staged", type: "datetime | null" },
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
      { key: "path", type: "str | null" },
      { key: "uri", type: "str | null" },
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
      { key: "sha256", type: "str" },
      { key: "duplicate_file_ids", type: "str[]" },
      { key: "chunk_index", type: "int" },
      { key: "start_offset", type: "int" },
      { key: "end_offset", type: "int" },
      { key: "text", type: "str" },
      { key: "embedding", type: "float[]", ml: true },
      { key: "entity_ids", type: "str[]", ml: true },
      { key: "mention_count", type: "int", ml: true },
    ],
  },
  {
    name: "Image",
    vector: true,
    fields: [
      { key: "id", type: "str" },
      { key: "file_id", type: "str" },
      { key: "width", type: "int" },
      { key: "height", type: "int" },
      { key: "camera_make", type: "str | null" },
      { key: "date_taken", type: "datetime | null" },
      { key: "gps_latitude", type: "float | null" },
      { key: "gps_longitude", type: "float | null" },
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
      { key: "address", type: "str | null" },
      { key: "file_id", type: "str | null" },
    ],
  },
  {
    name: "Person",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "name", type: "str | null" },
      { key: "aliases", type: "str[]" },
      { key: "date_of_birth", type: "datetime | null" },
      { key: "tags", type: "str[]" },
      { key: "is_verified", type: "bool" },
      { key: "source", type: "PersonSource" },
    ],
  },
  {
    name: "Face",
    vector: true,
    fields: [
      { key: "id", type: "str" },
      { key: "image_id", type: "str" },
      { key: "person_id", type: "str | null" },
      { key: "bounding_box", type: "FaceBoundingBox" },
      { key: "detection_confidence", type: "float | null", ml: true },
      { key: "quality_score", type: "float | null" },
      { key: "assignment_method", type: "FaceAssignmentMethod | null" },
      { key: "embedding", type: "FaceEmbedding", ml: true },
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
      { key: "match_method", type: "FaceMatchMethod" },
      { key: "status", type: '"pending" | "confirmed" | "rejected"' },
    ],
  },
  {
    name: "Entity",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "dataset_id", type: "str | null" },
      {
        key: "entity_type",
        type: '"person" | "organization" | "location" | "selector"',
      },
      { key: "display_name", type: "str" },
      { key: "aliases", type: "str[]" },
      { key: "source", type: "EntitySource" },
      { key: "is_verified", type: "bool" },
      { key: "person_id", type: "str | null" },
      { key: "location_id", type: "str | null" },
      { key: "selector_type", type: "SelectorType | null" },
    ],
  },
  {
    name: "Mention",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "entity_id", type: "str | null" },
      { key: "file_id", type: "str | null" },
      { key: "chunk_id", type: "str | null" },
      { key: "surface_text", type: "str" },
      { key: "entity_type", type: "EntityType | null", ml: true },
      { key: "normalized_value", type: "str | null" },
      { key: "start_offset", type: "int | null" },
      { key: "end_offset", type: "int | null" },
      { key: "extractor", type: "str | null" },
      { key: "extraction_confidence", type: "float | null", ml: true },
    ],
  },
  {
    name: "EntityRelationship",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "src_entity_id", type: "str" },
      { key: "dst_entity_id", type: "str" },
      { key: "relationship_type", type: "RelationshipType" },
      { key: "directed", type: "bool" },
      { key: "weight", type: "float | null" },
      { key: "source", type: "RelationshipSource" },
    ],
  },
  {
    name: "Event",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "file_id", type: "str | null" },
      { key: "event_type", type: "EventType" },
      { key: "title", type: "str" },
      { key: "date_start", type: "datetime" },
      { key: "date_end", type: "datetime | null" },
      { key: "extractor", type: "str | null" },
      { key: "confidence", type: "float | null", ml: true },
      { key: "is_verified", type: "bool" },
    ],
  },
  {
    name: "Location",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "latitude", type: "float" },
      { key: "longitude", type: "float" },
      { key: "geohash", type: "str | null" },
      { key: "name", type: "str | null" },
      { key: "address", type: "str | null" },
      { key: "country", type: "str | null" },
      {
        key: "source",
        type: '"name_mention" | "coordinate_mention" | "exif" | "geocoded" | "device_gps"',
      },
    ],
  },
  {
    name: "Comment",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "content", type: "str" },
      {
        key: "commentable_type",
        type: '"dataset" | "image" | "person" | "file" | "entity"',
      },
      { key: "commentable_id", type: "str" },
      { key: "user_id", type: "str" },
    ],
  },
  {
    name: "Enrichment",
    vector: false,
    fields: [
      { key: "id", type: "str" },
      { key: "enrichable_type", type: '"file" | "contact" | "image" | "face"' },
      { key: "enrichable_id", type: "str" },
      { key: "enrichment_type", type: "EnrichmentType", ml: true },
      {
        key: "status",
        type: '"pending" | "processing" | "completed" | "failed" | "skipped"',
      },
      { key: "retry_count", type: "int" },
      { key: "error_message", type: "str | null" },
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

// Entity / ontology / knowledge-graph layer. Mirrors
// libs/cipher-schemas/src/cipher/schemas/ontology.py and docs/ontology.md --
// keep the three in sync.
const ONTOLOGY_NODE_ATTRS = [
  "display_name",
  "aliases[]",
  "tags[]",
  "notes",
  "source",
  "is_verified",
  "person_id",
  "location_id",
  "selector_type",
];

const ONTOLOGY_ENTITIES: {
  name: string;
  description: string;
  attributes: string[];
}[] = [
  {
    name: "person",
    description:
      "Real-world individual of interest. Reuses the existing person table; the node bridges to it via entity.person_id, so faces stay reachable.",
    attributes: [
      "name",
      "aliases[]",
      "date_of_birth",
      "sex",
      "notes",
      "tags[]",
      "is_verified",
      "source",
    ],
  },
  {
    name: "organization",
    description:
      "Company, agency, or unit. Sub-units (regional offices, subsidiaries) are themselves organizations linked with part_of / subsidiary_of.",
    attributes: [
      "legal_name",
      "aliases[]",
      "category",
      "parent_id",
      "country",
      "notes",
    ],
  },
  {
    name: "location",
    description:
      "An address, a named place, or a geolocation from text or image EXIF. The point lives in the standalone PostGIS location table (the map viewer's source); the node bridges to it via entity.location_id.",
    attributes: [
      "address",
      "latitude",
      "longitude",
      "geohash",
      "source (name_mention | coordinate_mention | exif | geocoded | device_gps)",
      "precision_m",
      "country",
      "admin_area",
    ],
  },
  {
    name: "selector",
    description:
      "A strong identifier that resolves to one thing. Its own node so it can carry mentions and edges -- one phone shared across three files is one node. Unique per (dataset, kind, normalized_value).",
    attributes: [
      "selector_type",
      "raw_value",
      "normalized_value",
      "region_hint",
    ],
  },
];

const ONTOLOGY_SELECTOR_TYPES = [
  "phone",
  "email",
  "ip",
  "iban",
  "bank_card",
  "passport",
  "national_id",
  "imei",
  "imsi",
  "mac_address",
  "social_handle",
  "crypto_address",
  "license_plate",
  "domain",
];

const ONTOLOGY_RELATIONSHIPS: {
  type: string;
  from: string;
  to: string;
  symmetric?: boolean;
  description: string;
}[] = [
  {
    type: "has_selector",
    from: "person · organization",
    to: "selector",
    description: "An actor uses this phone / email / passport / handle / IBAN.",
  },
  {
    type: "member_of",
    from: "person",
    to: "organization",
    description:
      "Belongs to an organization (a club, gym, association, account). Produced from vCards and from membership emails (welcome, renewal, dues receipt) read by the events LLM pass, as suggestions.",
  },
  {
    type: "employed_by",
    from: "person",
    to: "organization",
    description:
      "Employed by an organization (or one of its units); role in attributes. Produced from email signatures and email domains, as suggestions.",
  },
  {
    type: "part_of",
    from: "organization",
    to: "organization",
    description:
      "A sub-unit (division, department, office) is part of a parent org; an org has at most one parent. Signature unit chains propose these.",
  },
  {
    type: "subsidiary_of",
    from: "organization",
    to: "organization",
    description: "An organization is a subsidiary of another.",
  },
  {
    type: "located_in",
    from: "person · organization · location",
    to: "location",
    description: "Located at / within a place.",
  },

  {
    type: "emailed",
    from: "person · organization · selector",
    to: "(same)",
    description:
      "Sender emailed recipient (to/cc/bcc); weight = emails sent that way, a reply is its own edge back. Endpoints are the bare email selectors, so links exist before names are known.",
  },
  {
    type: "called",
    from: "person · organization · selector",
    to: "(same)",
    description:
      "Caller phoned callee, from call records in a table; weight = calls placed that way.",
  },
  {
    type: "messaged",
    from: "person · organization · selector",
    to: "(same)",
    description:
      "Sender messaged recipient (SMS, chat exports); weight = messages sent that way.",
  },
  {
    type: "paid",
    from: "person · organization · selector",
    to: "(same)",
    description:
      "Payer transferred money to payee (bank exports); weight = payments that way, amounts on the edge.",
  },
  {
    type: "family_of",
    from: "person",
    to: "person",
    symmetric: true,
    description: "Two people are family.",
  },
  {
    type: "appears_in_photo_with",
    from: "person",
    to: "person",
    symmetric: true,
    description:
      "Two people's faces appear in the same photo (confirmed or pending face matches); weight = shared photos.",
  },
  {
    type: "co_mention_of",
    from: "any",
    to: "any",
    symmetric: true,
    description:
      "Two entities are mentioned in the same chunk of text; weight = shared chunks. For co-occurrence-style knowledge graphs -- available, but no producer ships yet. Not walked by default graph traversal.",
  },

  {
    type: "same_as",
    from: "any",
    to: "any",
    symmetric: true,
    description: "Two nodes asserted to be the same real-world thing.",
  },
  {
    type: "owns",
    from: "person · organization",
    to: "any",
    description: "An actor owns an asset, account, or other entity.",
  },
];

// Analyst-facing resolution terms -- keep in sync with docs/glossary.md "Resolution workflow".
const RESOLUTION_TERMS: [string, string][] = [
  [
    "Mention",
    "One occurrence of a name or identifier in a file — “Dell” in one email’s From header.",
  ],
  [
    "Name group",
    "Every unresolved mention of one name, counted together — “dell”: 639 mentions. One decision covers all of them.",
  ],
  [
    "Entity",
    "The single record for the real person, organization, location or identifier that mentions point at.",
  ],
  [
    "Auto-created entity",
    "An entity the resolver made for a name that matched nothing. Check it on the Verify tab.",
  ],
  [
    "Verify",
    "Keep an auto-created entity as a real one. Edit fixes its name. Each row lists the entities it may duplicate: merge folds it in (its name becomes an alias), keep apart says they differ.",
  ],
  [
    "Resolution",
    "A suggestion that a name group is a given entity, scored by the resolver, waiting for your decision.",
  ],
  [
    "Accept / Reject",
    "Take the suggested resolution (all the name’s mentions resolve to that entity) or say it is wrong.",
  ],
  [
    "Create new entity",
    "Make a new person, organization or location from the name group and resolve it there.",
  ],
  [
    "Not an entity",
    "Discard the name group — a slogan, a greeting, parser junk.",
  ],
];

function SectionEyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
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
      className="inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] font-mono text-muted-foreground transition-colors hover:border-primary/50 hover:bg-primary/10 hover:text-primary"
    >
      {icon}
      {label}
    </a>
  );
}

const FLOW_VARIANTS = {
  default: { border: "border-border bg-white/[0.02]", text: "text-foreground" },
  ml: {
    border: "border-annotation/50 bg-annotation/5",
    text: "text-annotation",
  },
  vector: { border: "border-primary/50 bg-primary/5", text: "text-primary" },
  muted: {
    border: "border-muted-foreground/40 bg-transparent",
    text: "text-muted-foreground",
  },
} as const;

function FlowNode({
  title,
  subtitle,
  variant = "default",
  optional = false,
}: {
  title: string;
  subtitle: string;
  variant?: keyof typeof FLOW_VARIANTS;
  /** Dashed border: runs only when chosen (or configured). */
  optional?: boolean;
}) {
  const styles = FLOW_VARIANTS[variant];
  return (
    <div
      className={cn(
        "flex min-w-32 flex-col items-center gap-0.5 rounded-lg border px-3 py-2.5 text-center",
        optional && "border-dashed",
        styles.border
      )}
    >
      <span className={cn("text-xs font-semibold", styles.text)}>{title}</span>
      <span className="font-mono text-[11px] text-muted-foreground">
        {subtitle}
      </span>
    </div>
  );
}

/** Every optional analytic, in pipeline order; title = service or `cipher` command. Text analytics need Extract first. */
const OPTIONAL_ANALYTICS: {
  stage: string;
  nodes: {
    title: string;
    subtitle: string;
    variant: keyof typeof FLOW_VARIANTS;
  }[];
}[] = [
  {
    stage: "Extract",
    nodes: [
      { title: "pyxberg · pyparse", subtitle: "text", variant: "ml" },
      { title: "pyvllm", subtitle: "OCR", variant: "ml" },
    ],
  },
  {
    stage: "Embed",
    nodes: [
      { title: "clir", subtitle: "text embeddings", variant: "ml" },
      { title: "setfitcv", subtitle: "image embeddings", variant: "ml" },
    ],
  },
  {
    stage: "Images",
    nodes: [
      {
        title: "extract-locations",
        subtitle: "EXIF GPS → map",
        variant: "default",
      },
      { title: "face", subtitle: "detect faces", variant: "ml" },
      {
        title: "match · cluster faces",
        subtitle: "faces → persons",
        variant: "ml",
      },
      {
        title: "link-face-cooccurrence",
        subtitle: "photo-with edges",
        variant: "default",
      },
      { title: "image heads", subtitle: "tag classifiers", variant: "ml" },
    ],
  },
  {
    stage: "Find mentions",
    nodes: [
      {
        title: "pyselectors",
        subtitle: "phones, emails, …",
        variant: "default",
      },
      { title: "gliner · nerd", subtitle: "entity names", variant: "ml" },
      { title: "pyprompt", subtitle: "LLM entities + events", variant: "ml" },
      {
        title: "pyparse .ics",
        subtitle: "calendar events",
        variant: "default",
      },
      { title: "pyparse .vcf", subtitle: "contacts", variant: "default" },
      {
        title: "extract-signatures",
        subtitle: "employer · unit · title",
        variant: "ml",
      },
    ],
  },
  {
    stage: "Resolve",
    nodes: [
      {
        title: "resolve-entities",
        subtitle: "one call: names · duplicates · places · links",
        variant: "default",
      },
      {
        title: "resolve-locations",
        subtitle: "places → gazetteer",
        variant: "default",
      },
      {
        title: "extract-relationships",
        subtitle: "emailed edges",
        variant: "default",
      },
      {
        title: "resolve-event-links",
        subtitle: "events → entities",
        variant: "default",
      },
    ],
  },
];

export default function DocsPage() {
  return (
    <div className="max-w-400 mx-auto px-6 relative pb-24 pt-5">
      <PageHeader
        eyebrow="Documentation"
        value="Platform overview"
        icon={<Braces size={14} className="text-primary/80" />}
      />

      {/* Masthead */}
      <div className="pb-10">
        <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
          Cipher
        </h1>
        <p className="mt-3 max-w-2xl text-base text-muted-foreground">
          A triage platform for unknown data. Point it at a pile of files,
          mailboxes, images, contacts, and calendars -- it types everything
          against defined schemas, runs AI/ML enrichment over it, resolves who
          and what is mentioned into entities, and makes the result searchable.
        </p>
        <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-muted-foreground">
          <span>
            API{" "}
            <b className="font-semibold text-foreground">
              FastAPI · cipher-serve
            </b>
          </span>
          <span>
            UI <b className="font-semibold text-foreground">Next.js</b>
          </span>
          <span>
            STORE{" "}
            <b className="font-semibold text-foreground">
              PostgreSQL · pgvector · pg_search · PostGIS
            </b>
          </span>
        </div>
      </div>

      <Separator />

      {/* Pipeline */}
      <section className="py-10">
        <div className="mb-6 flex items-center gap-2.5">
          <Workflow size={16} className="text-primary" />
          <SectionEyebrow>How a file becomes a record</SectionEyebrow>
        </div>
        <div className="flex flex-col">
          {PIPELINE.map((stage, i) => (
            <div
              key={stage.num}
              className={cn(
                "grid grid-cols-[3rem_1fr] gap-5 border-t border-border py-5 pl-3.5 border-l-2",
                i === 0 && "border-t-0",
                stage.ml ? "border-l-annotation/50" : "border-l-transparent"
              )}
            >
              <div className="pt-0.5 font-mono text-xl font-semibold text-white/15">
                {stage.num}
              </div>
              <div>
                <h3 className="mb-1 flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
                  {stage.title}
                  {stage.services.map((s) => (
                    <Badge
                      key={s}
                      variant="outline"
                      className="font-mono text-[11px] font-normal text-muted-foreground"
                    >
                      {s}
                    </Badge>
                  ))}
                </h3>
                <p className="max-w-2xl text-sm text-muted-foreground">
                  {stage.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <Separator />

      {/* File types */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <FileText size={16} className="text-primary" />
          <SectionEyebrow>What it ingests</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
          Six broad categories, each with its own parser and its own downstream
          enrichment. Extensions shown are representative, not exhaustive.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {FILETYPES.map((ft) => (
            <Card key={ft.name} className="ring-white/10">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-foreground">
                  <span className="text-primary">{ft.icon}</span>
                  {ft.name}
                </CardTitle>
                <CardDescription>{ft.description}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-1.5">
                  {ft.extensions.map((ext) => (
                    <span
                      key={ext}
                      className="rounded border border-border bg-white/[0.03] px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                    >
                      {ext}
                    </span>
                  ))}
                </div>
                <div className="border-t border-dashed border-border pt-2.5 font-mono text-[11px] text-muted-foreground">
                  handled by{" "}
                  <span className="font-semibold text-primary">
                    {ft.handler}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator />

      {/* Analytics services */}
      <section id="analytics" className="scroll-mt-16 py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Box size={16} className="text-primary" />
          <SectionEyebrow>Analytics services</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
          Each service is independently deployable and does exactly one job. Run
          them with the listed{" "}
          <span className="font-mono text-xs text-foreground">cipher</span>{" "}
          commands (order and flags in{" "}
          <span className="font-mono text-xs text-foreground">
            docs/running-analytics.md
          </span>
          ); from a dataset page you can request the ones that haven&apos;t run.
          Model / code links are placeholders.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {ANALYTICS.map((svc) => (
            <Card key={svc.name} className="ring-white/10">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="font-mono text-foreground">
                    {svc.name}
                  </CardTitle>
                  <Badge
                    className={cn(
                      "font-mono text-[11px] uppercase tracking-wide",
                      svc.role === "AI/ML"
                        ? "border-annotation/40 bg-annotation/10 text-annotation"
                        : "border-white/15 bg-white/5 text-muted-foreground"
                    )}
                    variant="outline"
                  >
                    {svc.role}
                  </Badge>
                </div>
                <CardDescription>{svc.description}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="rounded-md border border-border bg-white/[0.03] px-2.5 py-2 font-mono text-[11px] text-muted-foreground">
                  {svc.tech}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {svc.commands.map((command) => (
                    <span
                      key={command}
                      className="rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-foreground"
                    >
                      cipher {command}
                    </span>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {svc.links.model && (
                    <ServiceLink
                      href={svc.links.model}
                      label="Model"
                      icon={<Box size={12} />}
                    />
                  )}
                  {svc.links.code && (
                    <ServiceLink
                      href={svc.links.code}
                      label="Code"
                      icon={<Code2 size={12} />}
                    />
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator />

      {/* Architecture */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Database size={16} className="text-primary" />
          <SectionEyebrow>Architecture</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
          Staging always runs; every analytic after it is optional and chosen
          per dataset. Everything lands in one Postgres database that the API
          and frontend read. Elasticsearch is an optional alternative
          chunk-search backend (RETRIEVAL__BACKEND), off by default.
        </p>

        <Card className="ring-white/10">
          <CardContent className="flex flex-col items-center gap-3 py-6">
            <FlowNode title="Raw data" subtitle="unknown files" />
            <ArrowDown size={14} className="text-muted-foreground" />
            <FlowNode
              title="filetyper"
              subtitle="stage: type + hash"
              variant="ml"
            />

            <ArrowDown size={14} className="text-muted-foreground" />

            <div className="w-full rounded-xl border border-dashed border-border p-4">
              <p className="mb-3 text-center font-mono text-[11px] text-muted-foreground">
                optional analytics -- chosen per dataset
              </p>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
                {OPTIONAL_ANALYTICS.map((group) => (
                  <div key={group.stage} className="flex flex-col gap-1.5">
                    <span className="text-center text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {group.stage}
                    </span>
                    {group.nodes.map((node) => (
                      <FlowNode key={node.title} {...node} optional />
                    ))}
                  </div>
                ))}
              </div>
            </div>

            <ArrowDown size={14} className="text-muted-foreground" />

            <div className="flex flex-wrap items-center justify-center gap-2">
              <div className="flex flex-col gap-1.5 rounded-xl border border-border p-2">
                <span className="text-center text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Datastores
                </span>
                <FlowNode
                  title="Postgres"
                  subtitle="pgvector · pg_search · PostGIS"
                  variant="vector"
                />
                <FlowNode
                  title="Elasticsearch"
                  subtitle="optional, off by default"
                  variant="muted"
                  optional
                />
              </div>
              <ArrowRight
                size={16}
                className="shrink-0 text-muted-foreground"
              />
              <FlowNode title="FastAPI" subtitle="cipher-serve" />
              <ArrowRight
                size={16}
                className="shrink-0 text-muted-foreground"
              />
              <FlowNode
                title="Next.js frontend"
                subtitle="search · entities · graph · chat"
              />
            </div>

            <p className="max-w-md text-center font-mono text-[11px] text-muted-foreground">
              chat answers cite back into indexed records
            </p>
          </CardContent>
        </Card>

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 font-mono text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-annotation" /> AI/ML
            enrichment
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-primary" /> relational +
            vector
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-3 rounded-sm border border-dashed border-muted-foreground" />{" "}
            optional
          </span>
        </div>
      </section>

      <Separator />

      {/* Ontology */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Share2 size={16} className="text-primary" />
          <SectionEyebrow>Ontology</SectionEyebrow>
        </div>
        <p className="mb-3 max-w-2xl text-sm text-muted-foreground">
          A dataset is triaged into{" "}
          <span className="text-foreground">entities</span> and typed{" "}
          <span className="text-foreground">relationships</span> between them.
          Every entity is a thin node plus one detail row.
        </p>
        <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
          A{" "}
          <Badge
            variant="outline"
            className="border-annotation/40 bg-annotation/10 text-[11px] text-annotation"
          >
            mention
          </Badge>{" "}
          is evidence that an entity has one attribute value —{" "}
          <span className="font-mono text-xs">phone number</span> →{" "}
          <span className="font-mono text-xs text-foreground">
            selector.value
          </span>
          , <span className="font-mono text-xs">a name</span> →{" "}
          <span className="font-mono text-xs text-foreground">person.name</span>
          , <span className="font-mono text-xs">an address</span> →{" "}
          <span className="font-mono text-xs text-foreground">
            location.address
          </span>{" "}
          — anchored at a span in a document, image, or structured field. Not
          every mention resolves to an entity: a bare place or facility name
          with no coordinates stays unresolved until it is geolocated. Full
          reference:{" "}
          <span className="font-mono text-xs text-foreground">
            docs/ontology.md
          </span>
          .
        </p>

        <div className="mb-4 rounded-lg border border-border bg-white/[0.02] px-3.5 py-3">
          <span className="font-mono text-[13px] text-foreground">entity</span>
          <span className="ml-2 text-xs text-muted-foreground">
            shared node attributes
          </span>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ONTOLOGY_NODE_ATTRS.map((a) => (
              <span
                key={a}
                className="rounded border border-border bg-white/[0.03] px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
              >
                {a}
              </span>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {ONTOLOGY_ENTITIES.map((e) => (
            <Collapsible key={e.name}>
              <div className="rounded-lg border border-border bg-white/[0.02]">
                <CollapsibleTrigger className="group/trigger flex w-full items-center gap-2.5 px-3.5 py-3 text-left">
                  <Box size={15} className="shrink-0 text-primary" />
                  <span className="flex-1 font-mono text-[13px] text-foreground">
                    {e.name}
                  </span>
                  <ChevronRight
                    size={13}
                    className="shrink-0 text-muted-foreground transition-transform group-data-[state=open]/trigger:rotate-90"
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-none">
                  <div className="border-t border-dashed border-border px-3.5 py-3">
                    <p className="mb-2 text-xs text-muted-foreground">
                      {e.description}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {e.attributes.map((a) => (
                        <span
                          key={a}
                          className="rounded border border-border bg-white/[0.03] px-1.5 py-0.5 font-mono text-[11px] text-cyan-400"
                        >
                          {a}
                        </span>
                      ))}
                    </div>
                  </div>
                </CollapsibleContent>
              </div>
            </Collapsible>
          ))}
        </div>

        <div className="mt-3 rounded-lg border border-border bg-white/[0.02] px-3.5 py-3">
          <span className="font-mono text-[13px] text-foreground">
            selector_type
          </span>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ONTOLOGY_SELECTOR_TYPES.map((k) => (
              <span
                key={k}
                className="rounded border border-border bg-white/[0.03] px-1.5 py-0.5 font-mono text-[11px] text-cyan-400"
              >
                {k}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-5 mb-2 flex items-center gap-2">
          <Workflow size={14} className="text-primary" />
          <span className="text-xs font-semibold text-foreground">
            Relationship types
          </span>
        </div>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] text-left text-[12px]">
            <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-3 py-2 font-semibold">type</th>
                <th className="px-3 py-2 font-semibold">source</th>
                <th className="px-3 py-2 font-semibold">dest</th>
                <th className="px-3 py-2 font-semibold">description</th>
              </tr>
            </thead>
            <tbody className="text-muted-foreground">
              {ONTOLOGY_RELATIONSHIPS.map((r) => (
                <tr
                  key={r.type}
                  className="border-b border-border/60 last:border-0"
                >
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-foreground">
                    {r.type}
                    {r.symmetric && (
                      <span className="ml-1.5 text-[11px] text-muted-foreground">
                        ↔
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">
                    {r.from}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">
                    {r.to}
                  </td>
                  <td className="px-3 py-2">{r.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Separator />

      {/* Resolution workflow */}
      <section id="resolution" className="scroll-mt-16 py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Workflow size={16} className="text-primary" />
          <SectionEyebrow>Resolution workflow</SectionEyebrow>
        </div>
        <p className="mb-4 max-w-2xl text-sm text-muted-foreground">
          How extracted names become entities, in the words the Entities page
          uses. <b className="text-foreground">Verify</b> auto-created entities
          first, then <b className="text-foreground">Resolve</b> names to them.
        </p>
        <dl className="max-w-3xl divide-y divide-border/60 rounded-lg border border-border">
          {RESOLUTION_TERMS.map(([term, meaning]) => (
            <div
              key={term}
              className="flex flex-col gap-1 px-3.5 py-2.5 sm:flex-row sm:gap-4"
            >
              <dt className="text-sm font-medium text-foreground sm:w-48 sm:shrink-0">
                {term}
              </dt>
              <dd className="text-sm text-muted-foreground">{meaning}</dd>
            </div>
          ))}
        </dl>
        <Link
          href="/entities/resolution-guide"
          className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          Step-by-step guide <ArrowRight size={13} />
        </Link>
      </section>

      <Separator />

      {/* Schemas */}
      <section className="py-10">
        <div className="mb-1 flex items-center gap-2.5">
          <Braces size={16} className="text-primary" />
          <SectionEyebrow>Schemas</SectionEyebrow>
        </div>
        <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
          Every entity in Cipher is a typed Pydantic model shared across every
          service -- this is the shape a dataset decomposes into. Expand a
          schema to see its field shape; the{" "}
          <Badge
            variant="outline"
            className="border-annotation/40 bg-annotation/10 text-[11px] text-annotation"
          >
            vector
          </Badge>{" "}
          tag marks anything carrying an embedding.
        </p>

        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
          {SCHEMAS.map((schema) => (
            <Collapsible key={schema.name}>
              <div className="rounded-lg border border-border bg-white/[0.02]">
                <CollapsibleTrigger className="group/trigger flex w-full items-center gap-2.5 px-3.5 py-3 text-left">
                  <Braces
                    size={15}
                    className={cn(
                      "shrink-0",
                      schema.vector ? "text-annotation" : "text-primary"
                    )}
                  />
                  <span className="flex-1 font-mono text-[13px] text-foreground">
                    {schema.name}
                  </span>
                  {schema.vector && (
                    <Badge
                      variant="outline"
                      className="border-annotation/40 bg-annotation/10 text-[11px] uppercase tracking-wide text-annotation"
                    >
                      vector
                    </Badge>
                  )}
                  <ChevronRight
                    size={13}
                    className="shrink-0 text-muted-foreground transition-transform group-data-[state=open]/trigger:rotate-90"
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-none">
                  <pre className="overflow-x-auto border-t border-dashed border-border px-3.5 py-3 pl-9 font-mono text-[12px] leading-relaxed text-muted-foreground">
                    {schema.fields.map((f) => (
                      <div key={f.key}>
                        <span className="text-foreground">{f.key}</span>:{" "}
                        <span
                          className={f.ml ? "text-annotation" : "text-cyan-400"}
                        >
                          {f.type}
                        </span>
                      </div>
                    ))}
                    {schema.extends && (
                      <div className="mt-1 text-muted-foreground">
                        &#8627; {schema.extends}
                      </div>
                    )}
                  </pre>
                </CollapsibleContent>
              </div>
            </Collapsible>
          ))}
        </div>
      </section>

      <Separator />

      <div className="flex flex-wrap items-center justify-between gap-2 py-6 font-mono text-[11px] text-muted-foreground">
        <span>cipher/ -- UV workspace monorepo</span>
        <a
          href="/faq"
          className="inline-flex items-center gap-1.5 hover:text-primary"
        >
          <HelpCircle size={12} />
          More questions? See the FAQ
        </a>
      </div>
    </div>
  );
}
