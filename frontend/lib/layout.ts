/**
 * The one page-content measure for the app. Every route wraps its body in
 * `PAGE_CONTAINER`, and the shared `PageHeaderSlot` wraps its content in the
 * same thing — so the header eyebrow and the first row of page content always
 * share a left edge, on every screen and at every viewport width.
 *
 * Reading-width pages (docs, FAQ, settings, entity/person dossiers) keep this
 * outer container and left-align a narrower inner column with
 * `PAGE_READING` — the left edge still lines up, only the right margin grows.
 */
export const PAGE_CONTAINER = "mx-auto w-full max-w-400 px-6";

/** Narrower measure for prose / dossier columns. Left-aligned, never centered. */
export const PAGE_READING = "w-full max-w-5xl";
