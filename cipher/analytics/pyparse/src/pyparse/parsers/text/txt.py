from pathlib import Path

from pyparse.utils.text import clean_text


class TxtParser:
    @staticmethod
    def parse(
        file: Path | bytes,
        encoding: str = None,
        cleaned: bool = True,
    ) -> dict:
        """Parse a txt file."""
        if isinstance(file, bytes):
            encoding = encoding or "utf-8"
            text = file.decode(encoding=encoding)
        elif isinstance(file, (Path, str)):
            with open(file, encoding=encoding) as fb:
                text = fb.read()
        else:
            raise TypeError(f"Cannot parse {type(file)}")
        if cleaned:
            text = clean_text(text, extra_whitespace=True, trailing_punctuation=True)
        return text
