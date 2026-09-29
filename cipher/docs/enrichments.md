# Enrichments: staging boundary, dependency graph, time estimates

How a staged dataset is turned into an enrichment plan with rough time
estimates, so a triager can decide what is worth running. Vocabulary is in
`docs/glossary.md`; the step-by-step commands and run order are in
`docs/running-analytics.md`.

**One-line version:** staging (files loaded + typed) fixes the file inventory;
each enrichment's eligible slice of that inventory times a measured per-unit
throughput gives a rough wall-time estimate, shown on the dataset's page once
it's staged -- not in the ingestion request, which fires before any inventory
exists to estimate against.

---

## Two phases

| Phase | Command(s) | Writes | Milestone |
|---|---|---|---|
| **Stage** | `create-dataset`, `load-files` | `file` rows (`filetype`, `filetype_group`, `sha256`, `size`, uri) | `dataset.date_staged` |
| **Enrich** | `extract-text`, `embed-text`, `embed-images`, `detect-faces`, `extract-selectors`, `extract-entities`, `extract-events`, … | `enrichment` queue rows + domain rows; one `enrichment_run` per invocation | per-enrichment `progress` |

Staging is deliberately separate: it is cheap, deterministic, and produces the
inventory every estimate is computed against. A dataset is **staged** once it
has files; `date_staged` records when that first happened.

## Dependency graph

`ENRICHMENT_DEPENDENCIES` in `cipher/schemas/ingestion/enrichment.py` is the
single source of truth (also served at `GET /enrichments/config`). Hard
prerequisites only — an enrichment that reads rows a prior one produces:

- `text_embedding`, `selector_extraction`, `entity_extraction` ← `text_extraction`
- `ocr` ← `text_extraction` (PDFs only: OCR merges into the xberg row; images need nothing)
- `relationship_extraction` ← `entity_extraction`, `selector_extraction`
- `face_matching`, `face_clustering` ← `face_detection`

`enrichment_prerequisites(t)` returns the transitive, dependency-ordered set.
Both the dataset-request wizard and the estimates card use it: the wizard
auto-enables/disables prerequisites and dependents as you toggle an analytic
(`withPrerequisites` / `dependentsOf` in `request-types.ts`); the estimates
card lists each estimate's prerequisites.

## Estimates

Pure functions in `cipher/schemas/ingestion/estimation.py`:

1. **`estimate_workload(enrichment_type, inventory, params)`** — maps the
   `get_dataset_inventory` dict to the eligible unit count. Eligibility is by
   `filetype_group`: `image` for image/face/exif, `document` + `email` for the
   text family, `contact` for contact extraction. `face_matching` /
   `face_clustering` / `message_translation` are marked *not estimable* (they
   scale with data not visible in the file inventory).
2. **`resolve_rate(enrichment_type, device, measured, params)`** — the measured
   `RateStat` for that `(type, device)` when it has ≥ `MIN_SAMPLES_FOR_MEASURED`
   (5) runs, else the seeded `DEFAULT_RATES` entry. `concurrency` divides LLM
   wall time; `maxPages` caps document byte counts.
3. **`estimate_enrichment(workload, rate, progress)`** —
   `seconds = fixed_overhead + unit_count * seconds_per_unit`, with
   `low`/`high` from p25/p75 (measured) or ±40–80 % (seed). `confidence` is
   `measured` | `seeded` | `none`; `basis` is a human string.

`total_estimate_seconds(...)` sums a selected set (sequential execution).

### Where the throughput comes from

Every enrichment command in `cipher/orchestration/cli.py` is wrapped in
`record_run(...)` (`cipher/orchestration/run_recorder.py`), which writes an
`enrichment_run` row: `enrichment_type`, `dataset_id`, `device`, `unit`,
`unit_count`, `params`, `date_started/completed`, `duration_seconds`, `status`.
`PostgresEnrichmentRunRepository.get_rates()` computes median / p25 / p75
`duration_seconds / unit_count` per `(enrichment_type, device)`. So estimates
self-calibrate to whatever hardware the pipeline runs on — seeds first, then
measured once real runs accumulate.

Seed values are deliberately pessimistic and live in `DEFAULT_RATES`; adjust
them from `cipher rates` output as runs accumulate.

## Surfaces

| Surface | What |
|---|---|
| `GET /datasets/{id}/staging` | `is_staged`, `date_staged`, per-group counts/sizes |
| `GET /datasets/{id}/enrichment-estimates?device=cpu` | one `EnrichmentEstimate` per analytic, in pipeline order |
| `cipher estimate --dataset-name X [--device cuda]` | the same table on the CLI |
| `cipher rates` | measured rates + recent runs |
| `EnrichmentEstimates` card on `datasets/[id]` (`features/datasets/components/enrichment-estimates.tsx`) | **the only estimate UI.** ETA + eligible count + in-flight % per analytic, CPU/GPU toggle, "remaining to run" total, not-staged notice. Display-only -- no run trigger yet. |
| Dataset-request wizard (`features/datasets/components/dataset-create-form.tsx`) | **no estimates.** Fires before the dataset exists, so there's no inventory to estimate against. Collects an analytics *wishlist* (no numbers) for the GitHub issue, with dependency auto-enable/disable and required-param checks. |

## OCR

Two tiers, so a dataset is searchable without a GPU service and the heavy model is
only spent where it's needed.

**1. Inline, during `extract-text` (default, offline).** Every PDF's image-based pages
are recorded as `DocumentMetadata.image_pages` -- always, whatever OCR runs. They come
from xberg's own no-OCR per-page output: a page is image-based when xberg marks it
`is_blank`, or when its text layer has < 20 word chars (`is_blank` is exact, so a scan
carrying only a Bates stamp would otherwise slip through). PDFs with any are then
re-extracted OCRing *just those pages* with EasyOCR (`force_ocr_pages`; xberg's automatic
OCR decides per document and would re-read a mixed PDF's text-layer pages too) and records
`ocr_pages` / `ocr_model = "easyocr"`. Weights load from `--ocr-model-dir` /
`EASYOCR_MODEL_DIR` (`~/models/docling/EasyOcr`), so nothing is downloaded.
`--ocr-backend tesseract|none` switches engine or only records the pages;
`--ocr-language` is repeatable (EasyOCR codes: `en`, `fr`, …). The file viewer's text
tab flags image-based pages and which OCR produced them.

**2. `cipher ocr` (re-run with something better).** Multilingual OCR for image-based
PDF pages and images (incl. HEIF), via the `pyocr` analytic (jina-ocr-v1 on vLLM;
`make start-vllm` in `analytics/pyocr`). It replaces the EasyOCR text page-by-page
(only pyocr output is reused across duplicates). Run after `extract-text` (and
`embed-images` if filtering), before `embed-text` -- or later, then re-run `embed-text`:

```bash
cipher ocr --dataset-name X                                  # every PDF + supported image
cipher ocr --dataset-name X --filetype pdf --filetype heif   # restrict by filetype
cipher ocr --dataset-name X --clip-model-dir ~/models/transformers/clip-vit-base-patch16
```

- **Which pages:** pdfium reads each PDF page's text layer; pages with < 20 word chars
  (`--min-chars`) are *image-based* and go to the model, the rest keep xberg's text
  (`--force` OCRs everything). Every image/TIFF frame is OCR'd.
- **CLIP tag filter (opt-in):** zero-shot over the image embeddings `embed-images`
  already stored -- `--clip-tag` (text-bearing: screenshot, scanned document, receipt…)
  vs `--clip-negative-tag` (people, landscape…); an image is queued when ≥
  `--clip-threshold` of the probability mass is on the text-bearing tags. Filtered-out
  images stay unqueued, so a later unfiltered run still reaches them.
- **Output (one `ExtractedText` per file):** PDF pages are merged into the
  existing row page-by-page; images get a new row. `extractor=pyocr`,
  `metadata.ocr_pages` / `ocr_model` record provenance, HTML tables become
  `ExtractedTableInfo`, located figures become `DocumentStructureNode(node_type="figure")`
  with a normalized `BoundingBox` and a model-written caption (kept out of `content`).
  `prechunked` is one span per page, so chunks keep real page numbers.
- **Downstream:** written files are re-queued for `text_embedding` (images included --
  `embed-text` only *processes* `image`-group rows, OCR is what queues them). Mention
  producers (selectors/entities/events) are re-queued only for files that had no text
  before; files whose existing mentions now point at replaced text are reported.
- **Speed:** a rolling window of `--concurrency` files (default 32) keeps the GPUs fed;
  each service decodes every page of every in-flight file together. Content-identical
  files (sha256) are OCR'd once -- across runs and within a run. Multi-GPU = one service
  per GPU (`make start-vllm-all`, then one `--service-url` each); the client sends each
  file to the service with the fewest pages in flight. Measured on dense scanned pages
  (828 pages): 1× RTX 3090 5.6 pages/s, 2× 10.5 pages/s, both GPUs 99% busy, CPU ~30%.
  PDF rendering is 32 ms/page (~31 pages/s, overlapped) -- not the bottleneck.
  FastMTP speculative decoding is neutral at full batch (it mainly helps latency).
- **Photos without text:** jina-ocr-v1 writes a scene *description* instead of returning
  empty (seen on a pagoda photo) -- use the CLIP tag filter when a dataset has photos.
- `reset-text` also clears `ocr` rows (re-extraction overwrites the merged text).

## Adding an enrichment

1. Add the `EnrichmentType` member and any prerequisites in
   `schemas/ingestion/enrichment.py`.
2. In `estimation.py`: add it to `_UNIT`, `_ELIGIBLE_GROUPS` (or leave it out to
   mark not-estimable), `DEFAULT_RATES`, and `ESTIMATE_ORDER`.
3. Wrap its CLI command body in `record_run(...)` with the right `unit`.
4. If it takes tuning parameters in the wizard, add them to
   `ANALYTIC_PARAM_MODELS` (`schemas/ingestion/dataset_request.py`) and
   `features/datasets/request-types.ts`.
