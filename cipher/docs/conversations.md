# Conversations and repeated content

**Status:** conversation view built 2026-10-12 (migration 0053). Repeated images: not built.

**One-line version:** the email viewer gets a conversation rail built from the
`conversation_id` every email already has. Nothing new is fingerprinted or stored per file:
emails repeated across mailboxes are already caught by the meaningful hash, and repeated
images can be found from the CLIP embeddings already stored.

Vocabulary is in `docs/glossary.md` (**conversation**, **quoted block**, **meaningful hash**).

---

## 1. What exists today

| Signal | Where | Catches |
|---|---|---|
| `file.sha256` | staging | byte-identical files |
| `EmailMetadata.meaningful_hash` | `extract-text` (pyparse), index from mig 0052 | one message in several mailboxes ("same message as N other copies" in the email viewer). Empty on emails extracted before it existed: re-run `extract-text` on emails to fill it |
| `EmailMetadata.quoted_blocks` | pyparse | reply history and forwards inside an email's text, as offsets |
| `EmailMetadata.conversation_id` | pyparse (`X-GM-THRID`, `Thread-Index` root, else root `Message-ID`) | the conversation an email belongs to. Stored in `extracted_text.metadata`, but nothing queries it yet |

`rag` (2026-10-12): all 28,314 emails have a `conversation_id`. 908 conversations hold
2+ emails (3,034 emails). 2,201 single emails have a reply/forward subject but no partner.

## 2. Conversation view

**Index:** an expression index on `((metadata->>'conversation_id')) WHERE metadata ? 'conversation_id'`,
the same shape as the 0052 meaningful-hash index.

**Endpoint:** `GET /files/{id}/conversation` (next to `GET /files/{id}/email`) returns the conversation's emails ordered by
`date_sent`. Copies sharing a meaningful hash are collapsed to one. For each email it gives
sender, date, file id, and the first line of the text it adds (quoted blocks excluded).
Access goes through the existing dataset check.

**Linked by quoted text, computed at request time:** headers miss links when a conversation
crosses mail servers or clients (each side keeps its own thread id). So every open also looks
at emails in the same dataset with the same subject once reply prefixes are stripped
(`Re:` `Fwd:` `Fw:` `AW:` `WG:` `Отв:` `Пересл:` `回复:` `答复:` `转发:` `RE[2]:` …), sent within
**30 days**. A candidate joins only when it quotes, or is quoted by, an email already in the
conversation (the opening of one email's own text appears in the other's quoted block, the
same test `quoted_copies.py` uses to skip quoted copies in NER), followed through the chain.
A shared subject alone never links: two "Re: Weekly report" emails that don't quote each other
stay apart. The list is then labelled "linked by quoted text". Nothing is stored, so there is no
backfill or re-key. Quoted blocks are found on the text at request time, so this works on
emails extracted before quoted blocks were stored.

**View:** a conversation rail beside the message in `email-viewer.tsx`.
- Emails in date order, with the open one highlighted; a click switches the message.
- Quoted blocks in the open message collapse to "Show quoted text (from Megan, 3 Mar)".
- Header: "Conversation · 7 emails · 4 people".

The rail reuses existing list and mention-chip styles; there's no new nav entry.

## 3. Repeated images (optional)

If repeated photos (resized, recompressed, re-attached) clutter image search, add a
query-time check on the stored CLIP embeddings: similarity ≥ ~0.97 within the dataset, shown
as a "+N similar" chip that expands in place. It needs no new column, no pipeline change and no
backfill. Build it only if the clutter is noticed.

## 4. Not doing

**Text near-duplicate fingerprinting** (MinHash in `extract-text`, grouping, backfill) is
dropped. The data is mostly email, and the meaningful hash, quoted blocks and conversations
already cover its repeats. The extra columns, threshold tuning and `rekey` part aren't worth
their upkeep. Revisit if a document-heavy dataset shows many re-saved or edited copies.

## 5. Where it lives

- Index: migration `0053_email_conversation_id_index`.
- Subject keys: `pyparse.parsers.email.subjects` (`subject_key`, `strip_reply_prefixes`).
- Queries: `PostgresExtractedTextRepository.get_conversation_emails` / `get_subject_candidates`.
- Quote matching: `quoting_email` / `linked_by_quotes` in `cipher/orchestration/quoted_copies.py`.
- Route: `get_file_conversation` / `link_conversation` in `backend/.../routes/files.py`.
  `GET /files/{id}/email` also fills `quoted_blocks` on the parsed plain text, so the viewer can
  collapse quotes on emails extracted before quoted blocks were stored.
- UI: `features/emails/components/email-conversation.tsx` (rail) and `QuotedPlainText` in `email-viewer.tsx`.
  Quotes collapse in the plain-text view only; the HTML view is a sandboxed iframe.

`rag` (2026-10-12): the PARENT MEETING exchange (two header conversations from two mail servers)
shows the same 4 emails from any of them; 16 of 30 sampled orphaned replies were linked; median
40 ms per open.
