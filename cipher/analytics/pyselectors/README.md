# pyselectors

Deterministic (no ML) extraction and normalization of **strong selectors** from
free text and structured fields, for the CIPHER entity layer.

Supported selector kinds: `phone` (E.164 via `phonenumbers`), `email`, `iban`
(ISO 13616 mod-97 via `python-stdnum`), `imei` (Luhn), and passports found in a
machine-readable zone (MRZ) header line.

```python
from pyselectors import extract_selectors

for s in extract_selectors("Call +44 20 7946 0958 or write jo@acme.co.uk", language="en"):
    print(s.selector_kind, s.normalized_value, s.start_offset, s.end_offset)
```

Run as a service: `pyselectors-api` (`POST /extract`).

Named `pyselectors` (not `selectors`) to avoid shadowing the Python standard
library `selectors` module -- same reason `pyparse` / `pyxberg` carry the prefix.
