import gzip
from pathlib import Path

from cipher.utils.io import compute_hash
from pyparse.utils.io import safe_open


class GzipParser:
    """Gzip file parser.

    Gzip is a file compression format, not an archive format.
    But we can still extract the compressed file as a child File object.
    """

    @staticmethod
    def parse(
        file: Path | bytes,
        file_name: str = None,
        extract_children: bool = False,
        out_dir: Path = None,
        **kwargs,
    ):
        """Parse a gzip file."""
        out = {}
        if isinstance(file, bytes):
            out_file_name = (
                compute_hash(file, "md5") if file_name is None else file_name
            )
            if extract_children:
                out_path = out_dir / out_file_name
                with safe_open(out_path, "wb") as fb:
                    fb.write(gzip.decompress(file))
                out["path"] = out_path

        elif isinstance(file, (str, Path)):
            file = Path(file)
            out_file_name = Path(file.name.removesuffix(".gz"))
            if extract_children:
                with gzip.open(file, "rb") as fb:
                    out = {
                        "md5": compute_hash(fb, "md5"),
                        "file_name": str(out_file_name),
                        "file_extension": out_file_name.suffix,
                    }
                    out_file_name = out["md5"] + out.get("file_extension", ".bin")
                    out_path = out_dir / out_file_name
                    with safe_open(out_path, "wb") as fb_out:
                        fb_out.write(fb.read())
                out["path"] = out_path
        return {"children": [out]}
