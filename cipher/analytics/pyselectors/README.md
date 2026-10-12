# pyselectors

Deterministic (no ML) extraction of **strong selectors** from free text, for the
CIPHER entity layer. Five stages, all pure functions, everything precompiled and
cached -- ~1 ms per document, ~10 s for 10k docs single-threaded.

```
pattern match  ->  normalize  ->  validate (+ attributes)  ->  context score  ->  resolve overlaps
```

1. **pattern** -- per-type regexes from JSON packs (`packs/data/<type>.json`).
2. **normalize** -- Arabic/Persian digit folding (length-preserving, offsets stay
   valid), de-defang (`a AT b DOT com`), E.164, IBAN compaction, bech32
   lowercasing, profile-URL -> bare handle.
3. **validate** -- hard rules that drop the span on failure and pull out
   attributes: `phonenumbers` (region, carrier, geo, timezone, line type),
   `stdnum` (IBAN country, IMEI TAC, Luhn), `ipaddress` (version, private),
   vendored base58check / bech32(m) / EIP-55 / CryptoNote checksums for crypto.
4. **context score** -- a per-language weighted lexicon in the pack adjusts the
   base confidence using the words within a configurable per-direction window.
   No cue -> confidence stays at the pack base.
5. **resolve** -- overlapping spans collapse to the strongest by (priority,
   confidence, length); a specific subtype beats its umbrella.

```python
from pyselectors import extract_selectors, resolve_selector

# over a block of text
for s in extract_selectors("Call +44 20 7946 0958 or DM t.me/durov", language="en"):
    print(s.selector_type, s.selector_subtype, s.normalized_value, round(s.confidence, 2), s.attributes)

# retroactively, over a single bare value -- normalize + validate + attributes only
resolve_selector("020 7946 0958", selector_type=SelectorType.PHONE, region="GB")  # forced type
resolve_selector("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")  # type inferred
```

`resolve_selector` (and `POST /resolve`) run stages 2-4 on one value with no
surrounding text -- for an analyst pasting a raw selector, or the
`cipher rekey --selectors` sweep that brings stored selectors in line after a pyselectors
change (refreshes `attributes`, re-keys values that now normalize differently).

Phones: a number gets a country (and E.164) only when it states one (`+44 …`, `0044 …`,
`T + 1 646 …`) or the caller passes a verified `region`; otherwise it keeps its national
digits as written (`215.895.2372` -> `2158952372`, `number_format = national`) -- never a
country guessed from the text's language. In free text such a number needs a phone cue
(`Tel`, `Fax`, `phone` ...) nearby; extensions (`ext 8200`, `x12`) are dropped.

Selector `type` is the broad family (`phone`, `email`, `ip`, `iban`, `imei`,
`crypto_address`, `social_handle`, ...); `subtype` is the specific
network/platform (`btc_address`, `telegram`, ...). Enabled types live in
`packs/registry.py`; national-id / passport / IMSI / bank-card are Phase 2.

Run as a service: `pyselectors-api` (`POST /extract`).

Named `pyselectors` (not `selectors`) to avoid shadowing the stdlib `selectors`
module -- same reason `pyparse` / `pyxberg` carry the prefix.
