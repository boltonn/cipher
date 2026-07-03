import hashlib
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote, urlparse


class HashType(StrEnum):
    MD5 = "md5"
    SHA256 = "sha256"


def compute_hash(path: Path, algorithm: HashType, chunk_size: int = 65536) -> str:
    """Compute the hash of a file using the specified algorithm."""
    hash_func = hashlib.new(algorithm)
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def convert_st_time_to_datetime(st_time: float) -> datetime:
    """Convert a st_time (float) to a datetime object."""
    return datetime.fromtimestamp(st_time)


def fetch_bytes_from_uri(uri: str) -> bytes:
    """Fetch file content as bytes from file:// or s3:// URI."""
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()

    if scheme == "file" or scheme == "":
        path = Path(unquote(parsed.path))
        return path.read_bytes()

    elif scheme == "s3":
        raise NotImplementedError("S3 URI fetching not implemented yet.")
    else:
        raise ValueError(f"Unsupported URI scheme: {scheme}")
