// @/features/chat/types.ts

/** Which family of source a citation is (see backend `cipher/schemas/chat.py`). */
export type CitationKind = "document" | "email" | "person" | "dataset" | "entity" | "action";

/** A source the chat agent grounded its answer in.
 *
 * - `document` / `email`: a retrieved passage. Has `fileId` + offsets, opens the
 *   file viewer scrolled to the span.
 * - `person` / `dataset` / `entity`: a database record. Has `href`, an
 *   app-relative route the app navigates to. `entity` only has an `href` when it
 *   bridges to a person record.
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
