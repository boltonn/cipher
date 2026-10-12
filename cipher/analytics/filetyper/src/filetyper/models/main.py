from collections.abc import Callable, Generator
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from loguru import logger
from tqdm import tqdm

from cipher.schemas.ingestion.file import Compression, CompressionInfo, FileCreate
from cipher.utils.io import HashType, compute_hashes, convert_st_time_to_datetime
from filetyper.compression import PEEK_BYTES, gzip_header, is_tar, peek_decoded
from filetyper.encryption import is_encrypted
from filetyper.models.aiml import MagikaFileTyper
from filetyper.models.magic import MagicNumberFilterTyper
from filetyper.schemas import FileTypeInfo, FilteTyperStrategy

# Heuristic answers that only say "some text" (or nothing): magika is asked what kind.
GENERIC_FILETYPES = frozenset({"txt", "txtascii", "txtutf8", "txtutf16", "randomtxt", "randomascii", "unknown"})


class FileTyper:
    def __init__(self, registry_path: Path | None = None):
        self.custom = MagicNumberFilterTyper(registry_path=registry_path)
        self.ai = MagikaFileTyper()

    def map_mime_type_to_filetype_info(self, mime_type: str) -> FileTypeInfo:
        """Map a MIME type to FileTypeInfo using the custom registry."""
        return self.custom.map_mime_type_to_filetype_info(mime_type)

    def infer_path(
        self, path: Path, strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT, name: str | None = None
    ) -> FileTypeInfo:
        """Heuristics (magic bytes, then the name's extension), with magika refining what they leave generic.

        Args:
            path: The bytes to type.
            strategy: Heuristics only, magika only, or both (default).
            name: The file's real name when `path` doesn't carry it (a blob named by its hash).
        """
        return self._decide(lambda: self.custom.infer_path(path, name=name), lambda: self.ai.infer_path(path), strategy)

    def infer_bytes(
        self, data: bytes, strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT, name: str | None = None
    ) -> FileTypeInfo:
        """Like `infer_path` for bytes in memory; `name` supplies the extension heuristic."""

        def heuristic() -> FileTypeInfo | None:
            return self.custom.infer_bytes(data) or (self.custom.match_extension(Path(name).suffix) if name else None)

        return self._decide(heuristic, lambda: self.ai.infer_bytes(data), strategy)

    def infer_stream(self, stream: BinaryIO, strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT) -> FileTypeInfo:
        """Like `infer_bytes` for a seekable stream."""
        return self._decide(lambda: self.custom.infer_stream(stream), lambda: self.ai.infer_stream(stream), strategy)

    def _decide(
        self,
        heuristic: Callable[[], FileTypeInfo | None],
        model: Callable[[], FileTypeInfo],
        strategy: FilteTyperStrategy,
    ) -> FileTypeInfo:
        """Heuristics decide; magika refines only what they leave generic.

        Magika is asked when the heuristics find nothing or only "some text", and its answer is kept only
        when it is more specific (a `txt` that is really python, csv or an email).
        """
        found = heuristic() if strategy != FilteTyperStrategy.MAGIKA else None
        if strategy == FilteTyperStrategy.MAGIC_NUMBER or (found and found["filetype"] not in GENERIC_FILETYPES):
            return found or self.custom.map_mime_type_to_filetype_info("unknown")
        refined = self._registered(model())
        if found and refined["filetype"] in GENERIC_FILETYPES:
            return found
        return refined

    def _registered(self, info: FileTypeInfo) -> FileTypeInfo:
        """Magika's label in the registry's vocabulary (its group and mime), so one filetype has one group."""
        return self.custom.get_filetype_info(info["filetype"]) or info

    def infer(
        self,
        file: bytes | BinaryIO | Path,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
        name: str | None = None,
    ) -> FileTypeInfo:
        """Convenience method to infer file type from any supported input (`name` supplies the extension)."""
        if isinstance(file, Path) and file.is_file():
            return self.infer_path(file, strategy=strategy, name=name)
        elif isinstance(file, bytes):
            return self.infer_bytes(file, strategy=strategy, name=name)
        elif isinstance(file, BinaryIO):
            return self.infer_stream(file, strategy=strategy)
        else:
            raise ValueError(f"Unsupported file input type: {type(file)}")

    def get_file_info(
        self, path: Path, strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT, name: str | None = None
    ) -> dict:
        """Hashes, size and `describe` for a local file (hashes/size are of the file as found)."""
        hashes = compute_hashes(path, [HashType.MD5, HashType.SHA256])
        size = path.stat().st_size
        described = self.describe(
            md5=hashes[HashType.MD5], sha256=hashes[HashType.SHA256], size=size, path=path, name=name, strategy=strategy
        )
        return {**described, "md5": hashes[HashType.MD5], "sha256": hashes[HashType.SHA256], "size": size}

    def describe(
        self,
        *,
        md5: str,
        sha256: str,
        size: int,
        path: Path | None = None,
        data: bytes | None = None,
        name: str | None = None,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> dict:
        """Type, compression and encryption of one file as found (`path` or `data`, one of them).

        Args:
            md5: MD5 of the file as found.
            sha256: SHA256 of the file as found.
            size: Size of the file as found.
            path: Where the bytes are.
            data: The bytes, when they are in memory (an email attachment).
            name: The file's real name when `path` doesn't carry it (a blob) or there is no path.
            strategy: File type detection strategy.

        Returns:
            The `FileTypeInfo` fields plus `compression` (`CompressionInfo | None`) and `is_encrypted`.
        """
        if path is not None:
            type_info = self.infer_path(path, strategy=strategy, name=name)
        else:
            type_info = self.infer_bytes(data, strategy=strategy, name=name)
        with path.open("rb") if path is not None else BytesIO(data) as raw:
            inner, compression = self.see_through(
                type_info, raw, md5=md5, sha256=sha256, size=size, name=name or (path.name if path else None)
            )
            raw.seek(0)
            encrypted = compression is None and is_encrypted(raw, inner["filetype"])
        return {**inner, "compression": compression, "is_encrypted": encrypted}

    def see_through(
        self,
        type_info: FileTypeInfo,
        raw: BinaryIO,
        *,
        md5: str,
        sha256: str,
        size: int,
        name: str | None = None,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> tuple[FileTypeInfo, CompressionInfo | None]:
        """Type a single-stream compressed file by its decoded content (`report.csv.gz` is a csv).

        Args:
            type_info: The type inferred from the raw bytes.
            raw: The file as found, positioned at its start.
            md5: MD5 of the file as found.
            sha256: SHA256 of the file as found.
            size: Size of the file as found.
            name: The compressed file's name; less its compression suffix it names the content.
            strategy: File type detection strategy for the decoded content.

        Returns:
            The decoded content's type and how it was compressed, or `type_info` and None when it
            isn't compressed (or its content can't be told).
        """
        head = raw.read(PEEK_BYTES)
        raw.seek(0)
        if not (peeked := peek_decoded(raw, type_info["filetype"])):
            return type_info, None
        encoding, decoded_head = peeked
        filename, date_modified = gzip_header(head) if encoding == Compression.GZIP else (None, None)
        inner_name = filename or (Path(name).stem if name else None)
        inner = (
            self.custom.get_filetype_info("tar")
            if is_tar(decoded_head)
            else self.infer_bytes(decoded_head, strategy, name=inner_name)
        )
        if not inner or inner["filetype"] == "unknown":
            return type_info, None
        compression = CompressionInfo(
            encoding=encoding, md5=md5, sha256=sha256, size=size, filename=filename, date_modified=date_modified
        )
        return inner, compression

    def generate_from_local_path(
        self,
        path: Path,
        dataset_id: str,
        limit: int | None = None,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> Generator[FileCreate, None, None]:
        """Generate FileCreate objects from a local directory or single file.

        Args:
            path: Path to file or directory
            dataset_id: Dataset UUID to associate files with
            limit: Optional limit on number of files to process
            strategy: File type detection strategy

        Yields:
            FileCreate objects ready for database insertion
        """
        assert path.exists(), f"Path {path} does not exist."
        if path.is_file():
            file_paths = [path]
        elif path.is_dir():
            logger.debug(f"Scanning directory for files: {path}")
            file_paths = sorted([fp for fp in path.rglob("*") if fp.is_file()])
            logger.info(f"Found {len(file_paths)} files in directory {path}")
        else:
            raise ValueError(f"Path {path} is neither a file nor a directory.")

        if limit is not None:
            file_paths = file_paths[:limit]

        for file_path in tqdm(file_paths, desc="Processing files"):
            file_info = self.get_file_info(path=file_path, strategy=strategy)
            stat = file_path.stat()

            yield FileCreate(
                dataset_id=dataset_id,
                filename=file_path.name,
                path=file_path.resolve().as_posix(),
                uri=file_path.as_uri(),
                device=None,
                filetype_group=file_info["filetype_group"],
                filetype=file_info["filetype"],
                filetype_name=file_info.get("filetype_name"),
                md5=file_info["md5"],
                sha256=file_info["sha256"],
                mime_type=file_info["mime_type"],
                size=file_info["size"],
                date_created=convert_st_time_to_datetime(stat.st_ctime),
                date_last_updated=convert_st_time_to_datetime(stat.st_mtime),
                compression=file_info.get("compression"),
                is_encrypted=file_info["is_encrypted"],
            )

    def generate_from_s3_uri(
        self,
        dataset_id: str,
        bucket: str | None = None,
        prefix: str | None = None,
        limit: int | None = None,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> Generator[FileCreate, None, None]:
        """Generate FileCreate objects from S3 bucket/prefix.

        Args:
            dataset_id: Dataset UUID to associate files with
            bucket: Optional bucket name (overrides s3_uri)
            prefix: Optional prefix (overrides s3_uri)
            limit: Optional limit on number of files to process
            strategy: File type detection strategy

        Yields:
            FileCreate objects ready for database insertion
        """
        raise NotImplementedError("S3 support is not implemented yet")

    def __call__(
        self,
        source: Path | str,
        dataset_id: str,
        limit: int | None = None,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> Generator[FileCreate, None, None]:
        """Make FileTyper callable as a generator.

        Usage:
            file_typer = FileTyper()
            in_dir = Path("/data/images")
            for file_create in file_typer(in_dir, dataset_id):
                await repo.upsert_file(file_create)

        Args:
            source: Local Path or S3 URI string
            dataset_id: Dataset UUID to associate files with
            limit: Optional limit on number of files to process
            strategy: File type detection strategy

        Yields:
            FileCreate objects ready for database insertion
        """
        match source:
            case Path() if source.exists():
                yield from self.generate_from_local_path(source, dataset_id, limit, strategy)
            case str() if source.startswith("s3://"):
                yield from self.generate_from_s3_uri(source, dataset_id, limit=limit, strategy=strategy)
            case _:
                raise ValueError(
                    f"Unsupported source type: {type(source)}. Use Path for local files or 's3://' URI for S3."
                )
