# pygliner

Zero-shot, multilingual **entity and relation extraction** for the CIPHER entity
layer, wrapping [GLiNER](https://github.com/urchade/GLiNER) (entities) and
[GLiREL](https://github.com/jackboyla/GLiREL) (relations).

Both are *label-at-inference-time* models: the entity labels and relation labels
are passed with each request and come from the ontology
(`cipher.schemas.ontology.default_ner_labels()` /
`default_relation_labels()`), so extending the ontology is a label string, not a
retrain.

## When to use it vs. the alternatives

| service | model style | best at |
|---|---|---|
| `pyselectors` | deterministic (regex + checksums) | strong identifiers: phone, email, IBAN, IMEI, passport |
| **`pygliner`** | zero-shot (GLiNER + GLiREL) | long-tail / ad-hoc entity types and **relations**, multilingual, no training data |
| `nerd` *(separate repo)* | supervised / fine-tuned | high-precision **standard** entity types (PER/ORG/LOC/DATE...) where labelled data exists |

The `extract-entities` pipeline stage takes an `--extractor` switch and can run
any of these; `pygliner` is the default from Phase 2.

## Endpoints

```
pygliner-api            # NER_MODEL_DIR + optional RELATION_MODEL_DIR

POST /infer      {text, labels?, threshold?}                 -> [EntitySpan]
POST /relations  {text, entities, labels?, threshold?}       -> [RelationSpan]   # needs the `relations` extra
```

Install: `uv sync --extra fastapi --extra cpu` (add `--extra relations` for `/relations`).
