from collections.abc import Generator
from pathlib import Path
from typing import BinaryIO

from loguru import logger
from tqdm import tqdm

from cipher.schemas.file import FileCreate
from cipher.utils.io import HashType, compute_hashes, convert_st_time_to_datetime
from filetyper.models.aiml import MagikaFileTyper
from filetyper.models.magic import MagicNumberFilterTyper
from filetyper.schemas import FileTypeInfo, FilteTyperStrategy


class FileTyper:
    def __init__(self, registry_path: Path | None = None):
        self.custom = MagicNumberFilterTyper(registry_path=registry_path)
        self.ai = MagikaFileTyper()

    def map_mime_type_to_filetype_info(self, mime_type: str) -> FileTypeInfo:
        """Map a MIME type to FileTypeInfo using the custom registry."""
        return self.custom.map_mime_type_to_filetype_info(mime_type)

    def infer_path(self, path: Path, strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT) -> FileTypeInfo:
        """A smart, multi-strategy inference entry point."""
        # 1. Custom Strategy
        if strategy in (
            FilteTyperStrategy.MAGIC_NUMBER,
            FilteTyperStrategy.DEFAULT,
        ) and (info := self.custom.infer_path(path)):
            return info

        # 2. AI Fallback (if hybrid or ai_only)
        if strategy in (FilteTyperStrategy.MAGIKA, FilteTyperStrategy.DEFAULT):
            return self.ai.infer_path(path)

        # 3. Last Resort
        return self.custom.map_mime_type_to_filetype_info("unknown")

    def infer_bytes(self, data: bytes, strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT) -> FileTypeInfo:
        """Best for streams and small blobs."""
        if strategy in (
            FilteTyperStrategy.MAGIC_NUMBER,
            FilteTyperStrategy.DEFAULT,
        ) and (info := self.custom.infer_bytes(data)):
            return info

        if strategy in (FilteTyperStrategy.MAGIKA, FilteTyperStrategy.DEFAULT):
            return self.ai.infer_bytes(data)

        return self.custom.map_mime_type_to_filetype_info("unknown")

    def infer_stream(
        self,
        stream: BinaryIO,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> FileTypeInfo:
        """Infer file type from a stream. Magika can read from file-like objects."""
        if strategy in (
            FilteTyperStrategy.MAGIC_NUMBER,
            FilteTyperStrategy.DEFAULT,
        ) and (info := self.custom.infer_stream(stream)):
            return info

        if strategy in (FilteTyperStrategy.MAGIKA, FilteTyperStrategy.DEFAULT):
            return self.ai.infer_stream(stream)

        return self.custom.map_mime_type_to_filetype_info("unknown")

    def infer(
        self,
        file: bytes | BinaryIO | Path,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> FileTypeInfo:
        """Convenience method to infer file type from any supported input."""
        if isinstance(file, Path) and file.is_file():
            return self.infer_path(file, strategy=strategy)
        elif isinstance(file, bytes):
            return self.infer_bytes(file, strategy=strategy)
        elif isinstance(file, BinaryIO):
            return self.infer_stream(file, strategy=strategy)
        else:
            raise ValueError(f"Unsupported file input type: {type(file)}")

    def get_file_info(
        self,
        path: Path,
        strategy: FilteTyperStrategy = FilteTyperStrategy.DEFAULT,
    ) -> dict:
        """Infer file type and compute content hashes/size for a local file."""
        type_info = self.infer_path(path, strategy=strategy)
        hashes = compute_hashes(path, [HashType.MD5, HashType.SHA256])
        return {
            **type_info,
            "md5": hashes[HashType.MD5],
            "sha256": hashes[HashType.SHA256],
            "size": path.stat().st_size,
        }

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
