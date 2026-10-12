# Agentic search (chat) — triage redesign

**Status (2026-10-05):** proposal. Nothing here is built yet. The current agent
lives in `backend/src/cipher/api/agent/` (`core.py` prompt + loop, `tools.py`).

**Decision in one line.** The chat agent stays a *generic* research loop with no
question→tool recipes. Three things change around it: (1) the server does
the multi-angle searching in **one call** and reports coverage, (2) every
answer produces an **evidence set** that the analyst judges, and (3) the agent
**stops at checkpoints** where a human decision changes what it does next.
Its tools also cover everything a dataset can hold (files, folders, images,
events, places), not only email.

Terminology follows `docs/glossary.md`.

---

## 1. What it does today (measured)

Probe: local Qwen3.8-27B, `rag` (30.5k files: 28.3k email, 1.3k image, 530
document, 152 archive…), six questions nobody tuned for, run in-process.

| Question | What happened | Verdict |
|---|---|---|
| "What is in this data and where should I start?" | `search_passages` with no query (so it ranked by the question text and got Quora articles), then `count_emails` | Wrong frame. No orientation tool, so it described an email account and called it "belonging to Nicholas Bolton" (we never assume an owner). It didn't mention the 2.2k non-email files. |
| "Anything about money problems, debts or loans?" | 5 searches from different angles + 2 reads | Good answer, but 3 of the 5 result lists were mostly debt-relief spam. The `promotions` source tag was available as a filter and it didn't use it. The analyst sees 10 hits out of 647. |
| "What trips or travel happened in 2015?" | Left out `query`, then **ran the same search 6×** until the repeat guard stopped it | Never looked at the `event` table. It inferred a trip from a promo email ("implying the family took the trip"). |
| "Any passwords or credentials in here?" | Left out `query` **8×** (repeat guard ×2), then read 6 files | Found one real credential. Never tried `selector_type`, keyword mode, or documents/text files. A hard drive would have a `passwords.txt` that it can't find by filename. |
| "Most important people and how are they connected?" | **Crashed**: `read_file` hit 3 retries (`UnexpectedModelBehavior`) and the turn died | Fragile. |
| "House purchase or mortgage?" | 7 searches, with concrete words that improved each time (Pimmit, First Heritage, ratified) | Excellent. This is the loop working as designed. |

**Fixed 2026-10-07** (re-run of the same six questions): strict tool calling off in
pyvllm (searches without `query`: 6–8 per broad question → 0), thinking on for the
agent at medium effort with a 1k-token cap per step and earlier turns' reasoning not
re-sent (`agent/provider.py`), a context budget that counts this turn's reasoning
and compacts citations for the model (`agent/core.py` `fit_context`), entity
profiles without 100+ face ids, and `read_file` that returns notes instead of
killing the turn. All six now finish; peak prompt 15–18.6k of 24.5k (two used to
overflow); credentials found 3+ real values in 4–6 calls instead of 8 looping
ones. Still open from this list: orientation, non-email data, recall visibility,
noise defaults, and the agent calling the dataset "Nick Bolton's mailbox".

**Pattern.** When the question has concrete topic words, the loop works. It
fails on the questions that come first in triage: orientation, broad
sweeps, "what happened when", and structure. It also fails the same ways
every time:

1. **Query omission → looping — a serving bug, not the model.** Qwen *does*
   write the search terms (raw completions: `query` in 4/4 samples; its
   reasoning names them). vLLM 0.30 enables `VLLM_ENFORCE_STRICT_TOOL_CALLING`
   by default, and the `qwen_3_coder` grammar only accepts parameters **in
   schema order** (xgrammar check: `query` after `date_from` → rejected). Qwen
   habitually writes `date_from, date_to, limit` first, so `query` (first in
   our schema) is silently cut: 4/6 live calls lost it. Our tool then ranked by
   the question text, and the repeat guard fired. Every tool is exposed to this
   (any argument the model writes out of schema order is dropped). The parser
   itself handles any order, so turning strict mode off in pyvllm's `llm` env
   fixes it. Also: chat runs Qwen with thinking off, and 2 of 4 thinking runs
   overflowed the 24k context.
2. **Email-shaped world.** The prompt and tools assume mail (sent_from,
   count_emails). Filenames, folders, file types, images, events, places and
   tables can't be reached at all.
3. **Recall is invisible.** It shows 8–12 passages out of hundreds and gives no
   way to open the rest. For triage this is the biggest problem: the analyst
   can't tell "nothing there" apart from "the agent stopped looking".
4. **Noise isn't removed by default.** Promotions, spam and newsletters
   dominate personal mail, and `source_tags` / `message_states` exist but the
   agent doesn't use them.
5. **The human enters only at the end.** The output is prose. The analyst
   can't mark a hit as wrong, steer halfway through, or keep the result as a
   tagged set.
6. **One bad tool call kills the turn** (read_file retries).

---

## 2. Use cases

### 2.1 Dataset archetypes

The agent can't know the archetype in advance. It reads it from the
**dataset profile**, which already exists (`GET /datasets/profile`). The tools and
the first suggestions adapt to it; the loop itself does not change.

| Archetype | Looks like (profile signals) | What the analyst cares about |
|---|---|---|
| **Org mail server** (many mailboxes) | mostly email, many distinct header addresses on one or two internal domains, mailbox folders in paths | who knew what when; internal vs external; one thread across custodians' copies; unusual contacts; out-of-hours or deleted mail |
| **Personal mailbox / account export** | mostly email, one dominant correspondent cluster, heavy `promotions`/`updates` source tags | real people vs promotions and spam; accounts and services (selectors); money, travel, relationships; events |
| **Device / hard drive** | mixed filetype groups, deep folder tree, images + archives + app data, hashed or system filenames | folder structure; what's personal vs system noise; photos (faces, places, EXIF); credentials/keys files; documents by filename |
| **Office share / document collection** | mostly document + table, authored dates, version-like filenames | topics, projects, authors; near-duplicate drafts; tables with people/accounts; who wrote what |
| **Unknown / mixed** (the default) | anything | start with orientation, always |

### 2.2 Triage jobs (archetype-independent)

These are the jobs analysts do. They are **not** prompt recipes. Each one
just has to be possible with the tool surface (§4) and has a natural place for
a human checkpoint (§5).

| Job | Example asks | Primary tools | Human checkpoint |
|---|---|---|---|
| **Orient** | "what is this?", "where do I start?" | `describe_data`, `browse_folders` | pick a thread to pull |
| **Sweep a topic** (recall-first) | "anything about loans", "anything about the merger" | `sweep` → read → judge | scope/noise before reading; judge the set |
| **Find a needle** | "X's passport number", "when did they sign the lease?" | `sweep` (keyword-heavy), `find_files`, `read_file` | none if found; ask if two candidates |
| **Profile someone** | "who is Megan Flick?" | `find_entity`, `entity_profile`, `top_connections`, timeline | which of N same-name people |
| **Map a network** | "who are the key people", "who talks to outsiders" | `top_connections`, `count_emails`, `related_entities` | which cluster to expand |
| **Reconstruct a period** | "what happened in spring 2018", "trips in 2015" | `timeline` (events + dated hits), `count_emails` by month | which spike to open |
| **Sweep for sensitive material** | credentials, IDs, bank accounts, keys | `sweep` with `selector_type` / patterns, `find_files` by name | judge each hit (high stakes) |
| **Find media** | "photos of X", "pictures at the beach house" | `search_images`, faces of a person, places | confirm identity before tagging |
| **Curate** | "tag these as 'lease'", "these two are the same person" | `propose_tags`, `propose_entity_merge`, `propose_selector_links` | always: the agent only proposes |

---

## 3. Principles

- **Generic loop, structural help.** We still don't write question recipes.
  Fixes go into tool behaviour (server-side fan-out, defaults, in-result
  hints), not into longer prompts. The prompt gets *shorter*.
- **Recall is visible.** Every answer states its coverage and links to the
  full result set on `/search/[searchId]`.
- **The agent proposes; the analyst decides.** Relevance judgments, tags,
  links and merges are proposals (amber, `model` provenance) until a human
  accepts them.
- **Ask at checkpoints, not at random.** The agent asks only where the answer
  changes what it does next (§5).
- **Never assume an owner or custodian** (see feedback memory); ownership only
  from evidence in the files.
- **Degrade, don't die.** A bad tool call returns a note; it never ends the
  turn.

---

## 4. Tool surface

### 4.1 New / changed tools

| Tool | What it does | Built on |
|---|---|---|
| **`sweep`** (replaces the model calling `search_passages` N times) | Takes a list of *angles*: `{terms, mode}`, 1–5 of them, plus shared filters. The server runs every angle, with and without the person filter when one is set, de-duplicates by file, fuses the rankings (RRF) and returns: per-angle totals, the union total, the top N passages, and a `searchId` for the whole set. **Noise is excluded by default** (`exclude_source_tags=[promotions, social, forums]`, `exclude_message_states=[spam]`; on `rag` that's 10.4k promotions + 3.3k spam of 28k emails. `deleted` is *never* hidden, because it's a triage signal) and says so; `include_noise=true` turns that off. If `angles` is empty, it builds them from the question with rules (`read_query_filters` from global search). The model never sends an empty search. | `ChunkRetrievalRepository.search`, search records, `read_query_filters` |
| **`describe_data`** | The dataset profile, shortened: counts by filetype group, date histogram (as spans and peaks), top people/orgs, top correspondents, top places, top folders, how much is noise (source tags), and **what isn't searchable yet** (files with no extracted text, OCR pending, archives not expanded). Flags the archetype signals in §2.1 *as facts*, not as a label. | `PostgresDatasetProfileRepository.get_merged`, enrichment progress |
| **`browse_folders`** | Folder tree under a path with file counts by filetype group. | `file.browse_directory` / `count_folders` |
| **`find_files`** | Files by filename/path text, filetype or group, date range, tags, size. Metadata, not content. For "the spreadsheet called budget", "everything under /Users/x/Documents", "all .kdbx files". | `global_search.files_by_name`, `get_files_by_dataset` |
| **`timeline`** | For a period and/or entity: events (`event` table) plus counts of dated files per week/month, plus peaks. Use it for "what happened when"; it replaces inferring events from promo mail. | `event.list_events`, `count_emails`, chunk `date_content` |
| **`search_images`** | Text→image (CLIP), "photos with person X" (faces), with tags and date range. Image citations render as thumbnails. | image search, face search |
| **`propose_tags`** | Proposes a tag for a set of file ids with a one-line reason each. Rendered as a bulk-review card, and nothing is written until the analyst accepts. | `tag` table, `model` provenance on accept |
| `search_passages` | Kept for single precise follow-ups (exact phrase, one `file_id`). Docstring shortened. | — |
| `read_file` | Returns a note instead of raising on a bad id / no text (fixes the crash). Accepts a `query` to return the *relevant window* of a long file instead of the first 6k chars. | — |

Unchanged: `find_entity`, `entity_profile`, `entity_mentions`,
`related_entities`, `top_connections`, `count_emails`,
`explain_entity_resolution`, `propose_selector_links`,
`propose_entity_merge`, `ask_user`.

### 4.2 Tools follow the data

The profile is loaded once per turn into `ChatDeps`, and `prepare=` hides tools
that can't return anything for the selected datasets:

- no email → hide `count_emails`, and drop the email filters from `sweep`'s schema
- no images → hide `search_images`
- no events → `timeline` returns file counts only
- flat dataset (one folder) → hide `browse_folders`

This mechanism already exists (`_unless_looping`). It shrinks the schema the
24k-context model has to read, and it makes "email-shaped world" impossible
for a hard drive.

### 4.3 Prompt

The prompt goes from ~70 lines to ~25: role, the loop (orient if needed →
sweep → read → judge → answer with coverage), the output contract, and the
checkpoint rule. Everything tool-specific moves into tool docstrings and
in-result `note`s, which the small model follows more reliably.

---

## 5. Human in the loop

### 5.1 Check-ins

The agent stops (`ask_user`, already deferred to the browser) at exactly these
points. Everywhere else it proceeds and says what it assumed.

1. **Ambiguous identity**: two or more people behind one name with different
   results (exists today).
2. **Big result set before reading**: `sweep` total > ~50 files. The agent
   offers to **read the top 10**, **narrow** (it suggests the date peak / the
   folder / the person), or **hand over the list** (open `/search/[searchId]`).
   This is the main triage moment.
3. **Before any proposal** with more than a handful of items (tags, links).

A **Guided / Auto** toggle next to the model picker sets how strict this is.
Guided (the default) stops at all three. Auto stops only at the first and
otherwise answers with its best reading. The toggle is sent as a body field
(camelCase `autonomy`) and read into the instructions.

### 5.2 The evidence set

Every answer ends with an **Evidence** block (replaces the footer pills when
the turn ran a `sweep`):

```
Evidence · 4 searches · 647 files matched (412 after hiding promotions) · read 7
 ● Re: fairfax county tax — collections          Apr 2018  [relevant ✓ ✗]
 ● Liz Hughes — rent schedule                     Jan 2025  [relevant ✓ ✗]
 ○ Credit Card bills piling up? (promotion)       —         [not relevant ✓ ✗]
 Not searched: 152 archives not expanded · 84 images without OCR
 [Open all 412 in Search]  [Tag relevant as… ▾]
```

- The agent's judgment (relevant / not relevant + one-line reason) is shown in
  **amber** (annotation colour). The analyst's ✓/✗ replaces it.
- The analyst's ✓/✗ goes back into the **next request** as a short system
  note ("analyst marked these not relevant: …"). The agent uses it as feedback
  ("more like these, not those") without anything being stored.
- **Tag relevant as…** goes through `propose_tags` → the existing tag write
  path with `user` provenance, because the human clicked it. This is how a chat
  turns into a triaged, reusable set.
- **Open all in Search** → `/search/[searchId]`. The `sweep` already wrote
  that search record, so recall is one click away and nothing goes in the URL.
- **Not searched** comes from `describe_data`'s coverage gaps. The honest
  answer to "is there anything about X" includes what couldn't be looked at.

No new tables (see feedback memory): judgments live in chat state until the
analyst tags. Tags use the `tag` table. The set is a search record.

### 5.3 Plan visibility

The tool header already shows what was searched. For `sweep` it becomes
a compact plan chip row: `"loan owe borrowed" keyword · "worried about money"
semantic · 2015–2016 · promotions hidden`. Clicking **Edit** reopens it as
filter chips (the shared `ActiveFilters`) and **Re-run** sends the edited angles
as the next turn. The analyst can correct the agent's reading of the question
without retyping it.

---

## 6. Answer contract

1. Direct answer first, in a few sentences, attributed inline ("Ed Bolton, Apr 2018").
2. Then grouped findings (themes, or a timeline for period questions).
3. Then **coverage**: what was searched, how many matched, how many were read,
   and what wasn't searchable.
4. Then **what's next**: at most three concrete follow-ups (narrow to the peak,
   expand to a person's circle, check the archives). These come from the data,
   not from a template.
5. Distinguish **stated** from **inferred**. "A promo email mentions a 2015
   tour" is not "they went on the tour". The current prompt allows that
   inference, and the travel probe made it.

---

## 7. Evaluation

`scripts/eval_agent.py` (promoted from the scratch probe used for §1): runs
the agent in-process against the local LLM on a fixed question set per
archetype. For each question it records the tool trace, latency, repeat-guard
hits and crashes, and, where a golden file list exists, **recall@set** (did
the evidence set contain the known-relevant files). Questions are written
before tuning and kept separate from the prompt, so we don't overfit the
way the memory warns about.

Initial set: the six in §1, plus for each archetype in §2.1 one orient, one
sweep, one needle, one period and one structure question. Synthetic datasets
cover the archetypes `rag` doesn't (`org-chart-demo`, `signatures-demo`; an
office-share and an org-mail-server fixture still need to be made).

---

## 8. Build order

Each step ships on its own and is useful without the next.

1. ✅ **Make the loop reliable** (2026-10-10). `sweep` was dropped: plain `search_passages`
   is enough once the serving bug was fixed, so it was improved in place instead. An empty
   `query` now browses newest-first instead of ranking by the question. Promotions /
   social / forums mail and spam are left out by default (`include_promotions_and_spam`; Gmail's
   "updates" tab stays in, since it files bills, itineraries and security codes). Each
   search returns `openAll`: the exact search the text-search page runs. That page now
   takes `graphExpand` (the person-and-their-addresses filter) on
   `/search/{text,semantic,hybrid}`, so its totals match the agent's. Under each answer a
   summary line shows the searches run, files matched and files read, with "Open all in
   search". `read_file` is fixed; the prompt is shorter. `scripts/eval_agent.py`.
2. ✅ **Orientation and non-email data** (2026-10-10). `describe_data` gives file kinds,
   what isn't searchable, content dates, top people, mail flows, places and identifiers.
   `browse_folders` skips lone top folders. `find_files` searches by name, folder, kind,
   extension and date. Tools hide when the data has nothing for them (no email →
   `count_emails` hidden; no images, no events). The entity follow-up tools appear only
   once an entity has turned up. Enum docstrings are stripped from tool schemas. Fixed
   prompt: 6.4k tokens at the start of a conversation. Any tool error now comes back to
   the model as a note instead of ending the turn. The prompt says never to assume an
   owner, and to keep stated apart from inferred.
3. ✅ **Relevance judgments** (2026-10-10, simpler than the block sketched in §5.2). Each
   source pill's hover card has Relevant / Not relevant. The judgments travel with every later
   message (`relevance`) and go into the agent's instructions. They are not stored yet (§9). A bar above the input tags the
   relevant sources' files in one go (`POST /files/tag`, as the analyst). The agent doesn't
   propose tags itself. The conversation and marks survive leaving the page (a `Chat` held
   outside React), so "Open all" doesn't lose the thread.
4. ✅ **Check-ins + Guided/Auto** (2026-10-10). A toggle by the input sends `autonomy`. In
   Guided mode (the default), the first search of a turn matching > 50 files returns a
   check-in note, and every tool but `ask_user` pauses until the agent asks. The prompt
   alone wasn't enough: Qwen read past it. An answered `ask_user` now resumes with the
   page's settings (dataset scope, model, marks) instead of an auto-send without them.
   Not built: showing the agent's searches as filters the analyst can edit and re-run (§5.3).
5. **Period and media**: ✅ `find_events` (date-ordered, by participant/type/title) and
   `search_images` (CLIP with global search's background filter, shared helper
   `images_matching_text`). Still open: faces of a person, places.

---

## 9. Open questions

- **Noise defaults per archetype.** Hiding `promotions` is right for a personal
  mailbox. On an org mail server, vendor mail might be the case. Proposal:
  hide by default, always state it under the answer, and turn it off with one click.
- **Store relevance judgments** as retrieval training data: see §10.
- **Fusion across angles** uses plain RRF. Good enough to start; revisit if the
  eval shows semantic angles drowning out keyword hits.
- **Context budget.** `sweep` returns more than one search does today. Cap it at
  12 passages × 500 chars plus per-angle counts, and let the analyst open the rest.
- **Chat persistence.** Conversations live in the browser (`useChatStore`),
  so an evidence set doesn't survive another device. Fine for now, since tags
  and search records persist the parts that matter.

---

## 10. Relevance judgments as training data (future, not built)

**Today.** The analyst can mark a source the chat agent cited as relevant or not relevant.
The marks steer the agent's next reply and can tag the relevant files, then they're gone
(browser memory only).

**The idea.** Each mark is a *relevance judgment*: a labelled (query, passage, relevant /
not relevant) example, the standard material for improving and measuring search:

- **Measure search.** A growing test set of real queries with known-good and known-bad
  passages gives recall@k / nDCG for keyword vs semantic vs hybrid, and for every change to
  chunking, embeddings or fusion. `scripts/eval_agent.py` could score against it too.
- **Rerank.** Enough judgments train a small reranker over the top ~50 hits (cross-encoder
  on CPU, like the rest of the API), the cheapest quality gain.
- **Fine-tune embeddings.** Relevant passages are positives; not-relevant ones that ranked
  high are *hard negatives*, the most useful kind for contrastive training.

**What each judgment needs to keep.** The label only means something next to the exact
search that produced the passage, not the analyst's whole question:

| Field | Why |
|---|---|
| `query`, `mode`, filters | the search the passage answered (the agent's words, not the chat message) |
| `question` | the analyst's chat message, for question-level evaluation |
| `chunk_id`, `file_id`, `dataset_id` | the passage; chunk ids are content-keyed, so they survive re-embedding |
| `rank`, `score` | where it ranked, to find hard negatives |
| `is_relevant` | the label |
| `user_id`, `date_created` | who judged it (from the session, never the body) |

**Where it lives.** A new `relevance_judgment` table: nothing existing fits, since a tag
belongs to a file with no query, and a search record stores a query with no results. One row
per (user, query fingerprint, chunk); judging again replaces the label.

**Before building.** Citations would carry `chunkId` (they already do, for the UI) plus the
search that returned them (`searched` + rank), and the chat request would send judgments
with that context. The search pages could collect the same judgments later.

