from collections.abc import Iterator
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from cipher.utils.io import compute_hash
from pyparse.utils.io import safe_open


class ZipParser:
    @staticmethod
    def standardize_file_meta(info: ZipInfo):
        """Standardize the file meta."""
        date_modified = info.date_time
        file_sub_path = Path(info.filename)
        file_name = file_sub_path.name if file_sub_path else None

        return {
            "date_modified": datetime(*date_modified) if date_modified else None,
            "file_extension": Path(file_name).suffix if file_name else None,
            "file_name": file_name,
            "file_size": info.file_size,
            "file_uri": str(file_sub_path),
        }

    @staticmethod
    def extract(
        info: ZipInfo,
        archive: ZipFile,
        extract_children: bool = False,
        out_dir: Path = None,
        password: str = None,
        password_encoding: str = "utf-8",
    ) -> dict:
        """Extract a file from a zip archive."""
        password = bytes(password, encoding=password_encoding) if isinstance(password, str) else password
        child = ZipParser.standardize_file_meta(info)
        if extract_children:
            with archive.open(info, pwd=password) as fb:
                md5 = compute_hash(fb, "md5")
                child_extension = child.get("file_extension", ".bin")
                out_file_name = f"{md5}{child_extension}"
                out_path = out_dir / out_file_name
                with safe_open(out_path, "wb") as out:
                    out.write(fb.read())
            child["path"] = out_path.absolute()
        return child

    @staticmethod
    def stream(
        file_path: Path | BytesIO,
        extract_children: bool = False,
        out_dir: Path = None,
        **kwargs,
    ) -> Iterator[dict]:
        """Stream a zip file."""
        # create  an extract function with set parameters
        with ZipFile(file_path, mode="r") as archive:
            for info in archive.infolist():
                child: dict = ZipParser.extract(
                    info,
                    archive=archive,
                    extract_children=extract_children,
                    out_dir=out_dir,
                    **kwargs,
                )
                if child.get("path") and child["path"].is_file():
                    yield child
