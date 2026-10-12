// @/features/chat/types.ts

/** Which family of source a citation is (see backend `cipher/schemas/chat.py`). */
export type CitationKind =
  | "document"
  | "email"
  | "file"
  | "image"
  | "event"
  | "person"
  | "dataset"
  | "entity"
  | "action";

/** A source the chat agent grounded its answer in.
 *
 * - `document` / `email`: a retrieved passage. Has `fileId` + offsets, opens the
 *   file viewer scrolled to the span.
 * - `file` / `image`: a file found by its metadata or an image by what it shows. Has an
 *   `href` to the file's page.
 * - `event`: an extracted event. Has the `fileId` it came from, opened in the viewer.
 * - `person` / `dataset` / `entity`: a database record. Has `href`, an
 *   app-relative route the app navigates to.
 */
export interface ChatCitation {
  kind: CitationKind;
  displayName: string;
  snippet: string;
  score: number;

  // Passage citations (kind in {document, email}).
  chunkId?: string;
  fileId?: string;
  /** Kept for the document/email icon switch. */
  filetypeGroup?: "document" | "email";
  /** Document-only: page this passage came from, if known. */
  pageNumber?: number;
  /** Document-only: section heading hierarchy this passage falls under. */
  headingPath?: string[];
  startOffset?: number;
  endOffset?: number;
  /** Email-only: sender, "Name <address>". */
  sentFrom?: string;
  /** Email-only: to / cc recipients. */
  sentTo?: string[];
  /** Email-only: ISO datetime it was sent. */
  dateSent?: string;
  /** For a counted party (`count_emails`): its email count. */
  count?: number;

  // Record citations (kind in {person, dataset, entity}).
  targetId?: string;
  /** App-relative route the app navigates to, when linkable. */
  href?: string;
}

/** Citations open in-app (viewer dialog) except when they carry an `href`. */
export function isNavigableCitation(
  citation: ChatCitation
): citation is ChatCitation & { href: string } {
  return typeof citation.href === "string" && citation.href.length > 0;
}

/** The analyst's relevance judgment on a source: does it bear on the question? Sent back with the next message. */
export type Relevance = "relevant" | "notRelevant";

export interface JudgedSource {
  relevance: Relevance;
  displayName: string;
  fileId?: string;
}

/** A stable key for a source across tool calls and turns. */
export function citationKey(citation: ChatCitation): string {
  return citation.chunkId ?? citation.targetId ?? citation.fileId ?? `${citation.kind}:${citation.displayName}`;
}

/** How often the assistant stops to let the analyst steer (backend `ChatAutonomy`). */
export type ChatAutonomy = "guided" | "auto";
