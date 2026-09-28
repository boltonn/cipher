# pygliner

Zero-shot, multilingual **entity and relation extraction** for the CIPHER entity
layer, wrapping [GLiNER2.5](https://github.com/fastino-ai/GLiNER2) (the
`gliner2` package's boundary architecture). One checkpoint serves both tasks.

Both are *label-at-inference-time*: entity and relation labels are passed with
each request and come from the ontology
(`cipher.schemas.graph.ontology.default_ner_labels()` /
`default_relation_labels()`), so extending the ontology is a label string, not a
retrain. Relations run through GLiNER2's `JointIE` with each relation's head and
tail restricted to the entity labels its `RELATIONSHIPS` spec permits (e.g.
`employed by`: person → organization/company).

## When to use it vs. the alternatives

| service | model style | best at |
|---|---|---|
| `pyselectors` | deterministic (regex + checksums) | strong identifiers: phone, email, IBAN, IMEI, passport |
| **`pygliner`** | zero-shot (GLiNER2.5) | long-tail / ad-hoc entity types and **relations**, multilingual, no training data |
| `nerd` | supervised / fine-tuned | high-precision **standard** entity types (PER/ORG/LOC/DATE...) where labelled data exists |

## Model (offline)

Loads from a local directory only (`local_files_only`); the checkpoint bundles
its mDeBERTa encoder config and tokenizer, so nothing else is fetched.

```
huggingface-cli download fastino/gliner2.5-multi-v1 --local-dir ~/models/gliner/gliner2.5-multi-v1
```

## Endpoints

```
GLINER_MODEL_DIR=~/models/gliner/gliner2.5-multi-v1   # default
GLINER_MODEL_DEVICE=cpu
pygliner-api

POST /infer    {text, labels?, threshold?}                    -> [EntitySpan]
POST /extract  {text, labels?, relation_labels?, threshold?}  -> {entities: [EntitySpan], relations: [RelationSpan]}
```

Long text is chunked (384 words, 64 overlap) with offsets remapped to the full
input. Install: `uv sync --extra fastapi --extra cpu`.

## Threshold

Default `threshold=0.65` (`NerRequest`, `GlinerModel.infer`/`.extract`). Unlike
`nerd`, zero-shot confidence here is genuinely under-calibrated on real text --
measured precision climbs steadily with the floor (e.g. person: ~68% at 0.1 up
to ~96% at 0.85), so raising it is a real precision lever, not just a recall
tax. 0.65 is a reasonable general default; push higher for a precision-first
pass and accept the recall cost.
