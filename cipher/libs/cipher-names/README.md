# cipher-names

Multilingual personal-name toolkit for CIPHER entity resolution. Pure-CPU,
microsecond-scale, no model, no network. See
[`../../docs/entity-resolution.md`](../../docs/entity-resolution.md) §7 for the
design.

## Modules

| module | purpose |
|---|---|
| `script` | detect the dominant Unicode script of a string |
| `normalize` | `fold()` — NFKC, strip marks/controls, casefold, collapse whitespace/punctuation |
| `translit` | `to_latin()` — script → Latin (ICU when installed, else `anyascii`, else a built-in table) |
| `phonetic` | `phonetic_key()` — Metaphone-style key over the transliterated tokens |
| `nicknames` | `canonical_forms()` — hypocorism → formal given names (`Bob` → `Robert`) |
| `culture` | `Culture` enum + `infer_culture()` from region / language / script |
| `parse` | `ParsedName` + `parse_name()` — culture-aware given/surname/patronymic/particles split |
| `compare` | `compare_names()` — ordinal match level + per-component detail + a reason string |
| `keys` | `blocking_keys()` — the set of keys entity resolution blocks on |

## Install

`anyascii` + `jellyfish` are hard deps (both permissive, pure-Python wheels).
For best transliteration on Cyrillic/Arabic/CJK, add the `icu` extra
(`pip install cipher-names[icu]`, needs system `libicu`); everything works
without it at slightly lower recall.
