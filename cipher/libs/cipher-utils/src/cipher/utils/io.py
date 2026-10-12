import hashlib
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class HashType(StrEnum):
    MD5 = "md5"
    SHA256 = "sha256"


def compute_hash(path: Path, algorithm: HashType, chunk_size: int = 65536) -> str:
    """Compute the hash of a file using the specified algorithm."""
    return compute_hashes(path, [algorithm], chunk_size=chunk_size)[algorithm]


def compute_hashes(path: Path, algorithms: list[HashType], chunk_size: int = 65536) -> dict[HashType, str]:
    """Compute multiple hashes of a file in a single read pass."""
    hash_funcs = {algorithm: hashlib.new(algorithm) for algorithm in algorithms}
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            for hash_func in hash_funcs.values():
                hash_func.update(chunk)
    return {algorithm: hash_func.hexdigest() for algorithm, hash_func in hash_funcs.items()}


def convert_st_time_to_datetime(st_time: float) -> datetime:
    """Convert a st_time (float) to a datetime object."""
    return datetime.fromtimestamp(st_time)


def suffixed_path(path: Path, suffix: str, links_dir: Path) -> Path:
    """`path`, or a symlink to it in `links_dir` ending in `suffix`, for readers that type files by extension.

    Blobs are named by their hash alone; a reader such as xberg that picks its parser from the
    extension gets a link that carries one. No bytes are copied.

    Args:
        path: The file's local path.
        suffix: The extension the reader needs, with its dot (e.g. `.pdf`).
        links_dir: A scratch directory the caller removes when done.
    """
    if path.suffix or not suffix:
        return path
    link = links_dir / f"{path.name}{suffix}"
    if not link.is_symlink():
        link.symlink_to(path)
    return link
