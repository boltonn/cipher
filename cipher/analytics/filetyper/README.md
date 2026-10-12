# filetyper

## Decision Points

* This service was written to combine heuristics maintained in python via `filetype` library, extend it where needed, and use best of AI/ML in `Google's Magika` where filetype lacks specificity.

## How a file is typed (`FileTyper`, default strategy)

1. **Heuristics decide.** An empty file is `empty`; then magic numbers on the content (`data/registry.json`
   `magic`, with zip -> docx/xlsx/pptx disambiguation); then the extension of the file's **real name**. Bytes
   that don't live under their name (a blob, an attachment in memory) are typed with `name=`.
2. **Magika refines what the heuristics leave generic** -- nothing found, or only "some text" (`txt`,
   `txtutf8`, ...). Its label is kept only when it is more specific (a `.txt` that is really python or csv),
   and is read in the registry's vocabulary (one filetype, one group).
3. **`describe()`** adds `compression` (one single-stream layer seen through: `report.csv.gz` is a csv) and
   `is_encrypted` (zip member flags, PDF `/Encrypt`, encrypted Office packages).
