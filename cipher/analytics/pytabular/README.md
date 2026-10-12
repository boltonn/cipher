# pytabular

Profiles messy tabular files (csv/tsv, xlsx/xls/ods, parquet, json/jsonl) without loading them
into memory, and types their columns onto the CIPHER ontology: entity attributes (names, dates of
birth, addresses, coordinates, ...), selectors (phones, emails, IBANs, ...), edge attributes
(amounts, dates) and keys. It groups the typed columns into per-row entity **slots**
(`sender` = person[name, phone]) and proposes **edges** between them. The output is a
`TableMapping` (`cipher.schemas.ingestion.table_mapping`).

Design: [`docs/tabular-mapping.md`](../../docs/tabular-mapping.md).

## Detectors

Every detector scores a column against the field vocabulary (`data/field_types.json`), so they can
be compared and combined:

| detector     | cost              | what it looks at                                                    |
|--------------|-------------------|---------------------------------------------------------------------|
| `header`     | µs                | multilingual header synonyms (`data/header_lexicon.json`)           |
| `validators` | ms per column     | pyselectors, gazetteer, cipher-names, dates, coordinates, lexicons  |
| `gliner`     | GPU/CPU model     | GLiNER2.5 zero-shot classification of `header + sample values`      |
| `nerd`       | GPU/CPU model     | share of cells that are one whole person/org/location span          |
| `llm`        | local LLM call    | the whole table preview; also proposes roles (sender/receiver)      |

`decide.propose()` runs a cascade: cheap detectors first, models only for columns still ambiguous.
Columns, slots and edges a user set (`decision_source = user`) stay locked; everything else is
re-evaluated around them.

## Use

```bash
cipher profile-table path/to/file.xlsx                         # mapping JSON
cipher profile-table file.csv --mapping edited.json            # re-evaluate around user edits
cipher eval-table-typing                                        # synthetic messy tables
cipher eval-table-typing --labels labels.yaml --detectors header,validators,llm
make start                                                     # POST /profile
```

`labels.yaml`:

```yaml
- path: /data/subscribers.csv
  sheet: null                 # optional, Excel sheet name
  columns:                    # header text or `#<index>` -> field type
    "ФИО": person.full_name
    "#3": selector.phone
```
