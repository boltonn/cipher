# Signature extraction

`cipher extract-signatures` reads each email sender's signature: who they work for,
in which division or department, their title, and their work phone / email / website /
address. The results become reviewable suggestions on the organization page.

Code: `pipelines/cipher-orchestration/src/cipher/orchestration/extract_signatures.py`
(pipeline), `signature_cues.py` (word lists), `analytics/pyprompt/.../prompts/signature/v1.md`
(the prompt), `scripts/eval_signatures.py` (scoring on a synthetic multilingual set).

## The idea in one line

Rules decide **which emails are worth asking about** (cheap, recall-first); the LLM decides
**whether there really is a signature and what it says** (verbatim); plain code then **checks
everything the LLM returned** before anything is written.

## Step by step, for one email

```
From: Jonas Becker <becker@nordhafen-logistik.de>

Hallo zusammen,
anbei der überarbeitete Liegeplatzplan.

Mit freundlichen Grüßen

Jonas Becker
Leiter Disposition | Geschäftsbereich Kontraktlogistik
Nordhafen Logistik GmbH
Am Kai 4, 20457 Hamburg
+49 40 555 0101

Am 03.03.2025 um 09:00 schrieb Ulla Berg <berg@nordhafen-logistik.de>:
> ...
```

### 1. First pass -- is it worth asking? (rules, no model)

The LLM is the expensive part, so it only sees emails that could teach us something.

1. **Skip bulk mail.** Emails Gmail tagged promotions / updates / social / forums
   (`file.source_tags`) are newsletters and notifications, not people's signatures
   (`--include-bulk` reads them anyway). On `rag` that is 19k of 26k emails.
2. **Keep what the sender wrote.** Cut at the first reply/forward marker
   (`REPLY_MARKERS`: "On … wrote:", "Am … schrieb:", "-----Original Message-----",
   `>` quoted lines, …). Ulla's quoted message is gone.
3. **Take the tail**: the last 15 non-blank lines (≤ 2,000 characters).
4. **Keep it only if someone may sign off there *and* there is something to learn:**

   | Kind | Cue | Fires when | Here |
   |---|---|---|---|
   | signer | `farewell` | a line *is* a phrase in `FAREWELLS` ("Mit freundlichen Grüßen", "Best regards", "С уважением", "此致"…) | yes |
   | signer | `sender_name` | a short line is the sender -- by header name (nicknames, other scripts) or by the address spelling the name (`nbolton04@` ↔ "Nicholas C. Bolton") | yes |
   | signer | `ner_person` | NER (`extract-entities`) found a person in the tail | if NER ran |
   | payload | `ner_organization` | NER found an organization in the tail | if NER ran |
   | payload | `selector` | a phone number, a website (`www.` / `https://` / a bare `acme.com` line), or an email address other than the sender's | yes |

   "Thanks,\nNick Bolton" has a signer but no payload, so it never reaches the model.
   On `rag` this leaves ~1,300 of 28k emails (~5%).

### 2. Read -- is it a signature, and what does it say? (local LLM)

The tail plus `Sender: Jonas Becker <becker@…>` goes to the model with the `signature`
prompt. It answers `is_signature` -- false for newsletter footers, bare "Thanks, Nick",
and blocks signed by a brand or team -- and, if true, copies out (never translates):

```json
{"is_signature": true,
 "signature": "Jonas Becker\nLeiter Disposition | …\n+49 40 555 0101",
 "person_name": "Jonas Becker",
 "organizations": ["Nordhafen Logistik GmbH", "Geschäftsbereich Kontraktlogistik"],
 "role": "Leiter Disposition",
 "phones": ["+49 40 555 0101"], "addresses": ["Am Kai 4, 20457 Hamburg"]}
```

Organizations are **broadest first** (company → division → department); each level becomes
its own organization, linked `part_of` the one above.

**Repeats are free:** once Jonas's signature is known, any later email of his whose tail
contains it reuses this answer without a call.

### 3. Check (plain code)

Nothing the model says is trusted as-is:

- **Verbatim** -- every value must appear in the signature text, or it is dropped.
- **Has an organization** and **a person**, or there's no result.
- **Signer is the sender** (`signer_agreement`): the address spelling the signer's name, or the
  header name agreeing (given name too), confirms it; the header or address naming someone else
  (Edmond Bolton's account, Nicholas Bolton's signature) drops it; no information either way keeps
  it at lower confidence. A mismatch across writing systems is "no information" (田中 健二 vs
  "Kenji Tanaka").
- **Not a brand** -- a "person" that *is* the organization ("Kaggle" for Kaggle) is dropped.
- **Not a website** -- a bare domain (`fourthbrain.ai`) is not a company name.

### 4. Write (database)

Each value becomes a **mention** (with offsets, so it highlights in the email) and the links
become **mention relations**:

- Jonas `employed_by` Geschäftsbereich Kontraktlogistik (`role` = "Leiter Disposition")
- Geschäftsbereich Kontraktlogistik `part_of` Nordhafen Logistik GmbH
- Nordhafen Logistik GmbH `located_in` "Am Kai 4, 20457 Hamburg"
- the phone (and, when the signer is confirmed as the sender, the sending address) sit next
  to Jonas's name, so resolution links them to him (`has_selector`).

A sub-unit is matched only within its company ("Finance" at two companies never merges).
The email's `signature_extraction` enrichment is marked done (failed model calls retry next
run; `--rebuild` clears this workflow's output and re-reads everything).

### 5. Review (`resolve-entities`, then the organization page)

`resolve-entities` resolves the names. Each relation then shows on the organization page:

- both names settled → an ordinary suggestion (Accept / Reject);
- a name still unsettled → **"Names not settled yet"**: the review dialog shows the source
  emails and asks who each name is (the resolver's guess, someone else, or new -- preselected
  only when the person owns the sending address). Accepting settles the names, confirms the
  entities (no longer provisional) and adds the edge;
- the employer has no entity at all → **"Found in signatures"** on `/organizations`.

`resolve-entities` also proposes **email-domain** employment: when most signatures from a
domain name one organization, other senders from that domain are suggested, with the numbers.

## Adding a language

Edit `signature_cues.py` only (the payload cues -- phones, websites, NER -- need no words):

1. Add the language's sign-off phrases to `FAREWELLS` -- as people write them on their own
   line, lowercase, no trailing punctuation ("mit freundlichen grüßen", not "Mit freundlichen
   Grüßen,").
2. Add how its mail clients start a quoted reply to `REPLY_MARKERS` -- regular expressions,
   anchored on the fixed words ("Am .{0,200}schrieb.{0,80}:\s*$").
3. Run `uv run pytest pipelines/cipher-orchestration/tests/test_signature_cues.py` -- it checks
   every phrase matches and every pattern compiles.

The model already reads any language; the lists only decide which emails reach it. A missing
farewell costs recall only where the sender's name and NER cues don't fire either.

## Measuring

`scripts/make_signature_demo_emails.py` writes 67 synthetic emails in 8 languages (with quoted
replies, Latin-script headers over native-script signatures, divisions, addresses, and
colleagues who never sign); `scripts/eval_signatures.py` scores the pipeline on them without
writing anything:

```bash
uv run python scripts/eval_signatures.py --concurrency 8
```
