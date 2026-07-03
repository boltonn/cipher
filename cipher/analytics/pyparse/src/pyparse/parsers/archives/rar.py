from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from rarfile import RarFile, RarInfo

from pyparse.utils.io import safe_open
from cipher.utils.io import compute_hash


class RarParser:
    @staticmethod
    def standardize_file_meta(info: RarInfo):
        """Standardize the file meta."""
        file_sub_path = Path(info.filename)
        file_name = file_sub_path.name if file_sub_path else None
        date_modified_os = datetime(*info.date_time) if info.date_time else None

        return {
            "date_created": info.ctime,
            "date_modified": info.mtime or date_modified_os,
            "file_extension": Path(file_name).suffix,
            "file_name": file_name,
            "file_size": info.file_size,
            "file_uri": str(file_sub_path),
            # "system_os": info.file_host_os,
        }

    @staticmethod
    def stream(
        file_path: Path,
        extract_children: bool = False,
        out_dir: Path = None,
        password: str = None,
        **kwargs,
    ) -> Iterator[Any]:
        """Stream a rar file."""
        if not isinstance(file_path, Path):
            raise TypeError(f"Cannot parse {type(file_path)}")

        archive = RarFile(file_path)
        for member in archive.infolist():
            if member.is_file():
                child = RarParser.standardize_file_meta(member)
                child_extension = child.get("file_extension", ".bin")
                if extract_children:
                    with archive.open(member, pwd=password) as fb:
                        md5 = compute_hash(fb, "md5")
                        out_file_name = f"{md5}{child_extension}"
                        out_path = out_dir / out_file_name
                        with safe_open(out_path, "wb") as out:
                            out.write(fb.read())
                    # archive.extract(member, path=out_path.parent, pwd=password)
                    child["path"] = out_path.absolute()
                yield child
