# pyprompt

LLM **prompt-runner** for structured extraction over text in the CIPHER
pipeline. One process, many enrichment types, driven by repo-resident prompt
packs and an OpenAI-compatible model.

It is the model-backed counterpart to the deterministic / zero-shot extractors:

| service | style | best at |
|---|---|---|
| `pyselectors` | regex + checksums | strong identifiers (phone, email, IBAN, IMEI) |
| `pygliner` | zero-shot (GLiNER + GLiREL) | long-tail entity/relation types, no training data |
| `nerd` | supervised | high-precision standard entity types |
| **`pyprompt`** | LLM + structured output | free-text **event** extraction, nuanced relations, and any task expressible as a prompt |

## Prompt packs

Prompts live in the repo under `src/pyprompt/prompts/<task>/vN.md` — a small
`key: value` frontmatter block, then `<<SYSTEM>>` / `<<USER>>` sections that are
Jinja2 templates. Registered in `prompts/registry.py` against the Pydantic model
the model must return. Shipped inside the wheel.

Current packs: **`entities`** (NER + directed relations) and **`events`**
(calendar events with participants, places, a typed `details` blob, and a
`confidence`; pass `reference_date` to anchor relative dates).

Every request can also carry a `prompt` field that overrides the pack's
template while keeping the typed output contract; `POST /run` drops the pack
entirely and takes an arbitrary prompt plus an optional JSON Schema.

## Config

Same env contract as the chat backend (`LLM__*`), resolved through
`LLMSettings.openai_client_kwargs()` so `local` behaves identically in both:

```
# OpenAI
LLM__PROVIDER=openai
LLM__MODEL=gpt-4o-mini
LLM__API_KEY=...                # falls back to OPENAI_API_KEY

# the repo's local vLLM Gemma server (~/llm, `make start` there)
LLM__PROVIDER=local
LLM__MODEL=gemma-3n-E2B-it
# LLM__BASE_URL defaults to http://localhost:8002/v1; key is not needed

PROMPT_TEMPERATURE=0.0
PROMPT_MAX_RETRIES=2
PROMPT_MAX_INPUT_CHARS=48000
PROMPT_REQUEST_TIMEOUT=90        # raise to 300+ for a slow local model
```

`LLM__PROVIDER=google` / `anthropic` are **not** usable here — pyprompt speaks
only the OpenAI wire format. Point `LLM__BASE_URL` at a compatible gateway if you
need those.

## Endpoints

```
pyprompt-api

POST /entities  {text, labels?, relation_labels?, prompt?, model?}          -> {entities: [EntitySpan], relations: [RelationSpan]}
POST /events    {text, reference_date?, prompt?, model?}                    -> {events: [ParsedEvent]}
POST /extract   {text, tasks?, labels?, relation_labels?, reference_date?}  -> {entities: {...}, events: {...}}
POST /run       {prompt, text?, system?, json_schema?, model?}              -> parsed object | {text}
```

`/extract` (the **`extract`** pack) runs entities/relations and/or events in a
single structured call -- `tasks` (default `["entities", "events"]`) gates which
prompt sections and output fields are produced. Orchestration consumes it
in-process via `PromptRunner.extract_all(...)` from `cipher extract-llm`.

Entity character offsets are resolved server-side by locating each surface
string in the analyzed text (an LLM does not count characters), so the output
is the same `EntitySpan` / `RelationSpan` contract the ingestion pipeline
already consumes.

Install: `uv sync --extra fastapi`.

## In the pipeline

Consumed in-process (not over HTTP) by orchestration:

- `cipher extract-entities --extractor llm` → `name`/attribute `mention` rows,
  fed to `resolve-entities`.
- `cipher extract-events --llm` → `event` rows (`extractor = "llm"`) from email
  bodies, alongside the deterministic `.ics` path.
- `cipher extract-llm --tasks entities,events` → both of the above from **one**
  `extract_all(...)` call per file, completing both enrichments together. It runs
  `--concurrency` calls at once, logs an ETA, and refuses a run over
  `--max-files` (15k) without `--yes`.

**Model choice for bulk passes.** Serve a standard ~7–30B instruct model (vLLM /
TGI) or use a cloud model. Tiny models such as `gemma-3n-E2B` run ~20–40× slower
than a normal dense model under vLLM (~95 tok/s on a 3090) and also over-generate
under a large structured schema — fine for a spot check, unusable for a dataset
of any size. For a slow local model also raise `PROMPT_REQUEST_TIMEOUT`
(a 24B GGUF at ~20 tok/s can exceed the 90 s default on a long email), drop
`PROMPT_MAX_RETRIES` to 1, and trim `PROMPT_MAX_INPUT_CHARS`.
