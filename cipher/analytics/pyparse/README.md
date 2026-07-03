# pyparse

## Config

```bash
HOST="0.0.0.0"
PORT=8080
RELOAD=true
LOG_LEVEL="INFO"
```

## Decision Points

* **aspose** has native .NET parsers for old Microsoft Office products. It is faster than LibreOffice conversion and extraction but it requires a license for larger files. We could extract and then remove the boilerplate text and try and catch licensing errors as an alternative but it seems not worth it.

## TODO

* bz2
