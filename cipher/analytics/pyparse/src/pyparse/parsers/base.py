from datetime import datetime
from pathlib import Path

from cipher.schemas.file import FileBase


def get_file_instance(file: Path | str) -> dict:
    """Get metadata about the file."""
    if isinstance(file, (str, Path)):
        return get_file_instance_from_path(file)
    raise NotImplementedError(f"Type {type(file)} not supported for get_file_instance")


def get_file_instance_from_path(file: Path | str) -> dict:
    """Get metadata about the file."""
    path = Path(file).absolute()
    file_stat = path.stat()

    return FileBase(
        uri=path,
        date_modified=datetime.fromtimestamp(file_stat.st_mtime),
        date_created=datetime.fromtimestamp(file_stat.st_ctime),
        filename=path.name,
    )
