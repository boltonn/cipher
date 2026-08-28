from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from tarfile import TarFile, TarInfo

from cipher.utils.io import compute_hash
from pyparse.utils.io import safe_open


class TarParser:
    @staticmethod
    def standardize_file_meta(info: TarInfo):
        """Standardize the file meta."""
        info: dict = info.get_info()
        date_modified = info.get("mtime")
        if date_modified:
            date_modified = datetime.fromtimestamp(date_modified)
        file_sub_path = Path(info.get("name"))
        file_name = file_sub_path.name if file_sub_path else None

        return {
            "date_modified": date_modified,
            "file_extension": Path(file_name).suffix,
            "file_name": file_name,
            "file_size": info.get("size"),
            "file_uri": str(file_sub_path),
        }

    @staticmethod
    def stream(
        file_path: Path,
        encoding: str = None,
        extract_children: bool = False,
        out_dir: Path = None,
        **kwargs,
    ) -> Iterator[dict]:
        """Stream a tar file."""
        if not isinstance(file_path, Path):
            raise TypeError(f"Cannot parse {type(file_path)}")

        archive = TarFile(file_path, encoding=encoding)
        for member in archive.getmembers():
            if member.isfile():
                child = TarParser.standardize_file_meta(member)
                if extract_children:
                    with archive.extractfile(member) as fb:
                        md5 = compute_hash(fb, "md5")
                        child["md5"] = md5
                        child_extension = child.get("file_extension", ".bin")
                        out_file_name = f"{md5}{child_extension}"
                        out_path = out_dir / out_file_name
                        with safe_open(out_path, "wb") as out:
                            out.write(fb.read())
                    # archive.extract(member, path=out_dir)
                    child["path"] = out_path.absolute()
                yield child
        archive.close()
