# nerd

Supervised multilingual NER for the CIPHER entity layer: a fine-tuned
transformers **token-classification** model (XLM-RoBERTa family, WikiNeural, or a
locally-trained `nerd-*` checkpoint). Ported from the standalone `nerd` repo into
the `analytics/*` workspace pattern.

## When to use it vs. the alternatives

| service | model style | best at |
|---|---|---|
| `pyselectors` | deterministic (regex + checksums) | phone, email, IBAN, IMEI, passport |
| `pygliner` | zero-shot (GLiNER2.5) | long-tail / ad-hoc types **and relations**, no training data |
| **`nerd`** | supervised / fine-tuned | high-precision **standard** types (person / organization / location / date / …) where labelled data exists |

`extract-entities` takes an `--extractor` switch; all three emit the shared
`cipher.schemas.spans.EntitySpan`.

## Run

```
NERD_MODEL_DIR=~/nerd/deps/nerd-c28-v0   # or a HuggingFace id
NERD_MODEL_DEVICE=cpu
nerd-api                                  # POST /infer {text, threshold?}
```

The HF pipeline's `entity_group` labels are normalized and mapped to ontology
types via `nerd.labels` (`PERSON`/`PER` → person, `ORG` → organization,
`GPE`/`LOC`/`FAC` → location, everything else passed through as a raw label).

Decoding pools sub-word predictions to whole words first (`NerdModel._pool_words`,
HF's `"first"` aggregation) before BIO-merging -- this is what keeps a mid-word
tag flip (e.g. "Delaware" as "Dela"+"ware") from truncating the span. Measured
on real + gold data, the model's confidence is already well-calibrated at the
default `threshold=0.5` (88-99% precision across languages) -- raising it buys
almost no precision and steadily costs recall, so leave it at 0.5.

## Training

`src/nerd/data/` holds the dataset processors (OntoNotes v5, MultiNERD, UNER,
DeepPavlov). Install the `train` extra and see `nerd.data.summary`.
