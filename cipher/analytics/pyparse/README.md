# pyparse

Readers for message and record formats -- email (`.eml`, Outlook `.msg`), calendar (`.ics`),
contacts (`.vcf`), HTML -- into `cipher-schemas` models. Documents go through xberg and
archives through pyarchive; pyparse doesn't do either.

## Design

- **Functions, not classes.** Each format exposes `parse_*(source, *, ...)`, plus `iter_*` for
  files holding many records. Nothing is constructed per call; the one costly helper (a
  `FileTyper`, ~30 ms to build) is shared per process (`pyparse.children.shared_file_typer`).
- **Typed, keyword arguments.** Everything after the source is keyword-only; options that
  shape *how* to read travel in one model (`EmailOptions`), separate from the input.
- **Children go to a sink.** Attachments, winmail.dat contents and inline HTML images are
  handed to a `ChildSink` (`(*, data, filename) -> FileBase`); the parser never decides where
  bytes are stored. Default `describe_only` types and hashes them; `DirectorySink` writes them
  to a folder; the cipher email step's sink writes into the output store with `path` =
  `<email path>/<filename>` (where it was found).
- **Dispatch by filetyper name.** `parse_email(source, filetype=...)` picks the reader from
  `READERS` (`SUPPORTED_FILETYPES` derives from it).
- **Logging, not printing.** Skipped parts (no payload, undecodable inline image, unmapped vCard
  field) log via loguru; progress bars belong to the loops that call pyparse (the cipher steps).

| Format | Entry points | Extra |
|---|---|---|
| Email | `parse_email(source, *, filetype, sink, options)`, `parse_eml`, `parse_msg` | `email` |
| Calendar | `parse_events(file, *, encoding)`, `iter_events(stream, *, encoding)` | -- |
| Contacts | `parse_contacts(file, *, encoding)`, `iter_contacts(stream, *, encoding)` | `contacts` |
| HTML | `html_to_text`, `sanitize_html(*, config)`, `extract_links(*, replacement_tag)`, `parse_html(*, method, sink)` | `html` |

```python
from pyparse.children import DirectorySink
from pyparse.parsers.email import EmailOptions, parse_email

email = parse_email(raw, filetype="eml", sink=DirectorySink(out_dir=out), options=EmailOptions(sanitize_html=True))
```

Email specifics live beside the reader: S/MIME (`smime.py`), TNEF / winmail.dat (`winmail.py`),
RTF bodies (`rtf.py`), quoted replies (`quotes.py`), subjects (`subjects.py`), the
cross-mailbox message key (`meaningful_hash.py`), embedded Outlook items (`msg_embedded.py`).
