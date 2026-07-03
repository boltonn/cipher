import subprocess
from pathlib import Path
from uuid import uuid4

from loguru import logger


def convert_with_libre(
    file_path: Path, tmp_dir: Path, target_format: str, timeout: int = 10
):
    """Convert a file to a target format using libreoffice.

    Note: This is meant to be used as a fallback against temp files or
    directories since LibreOffice does not have permission to write to
    anywhere other than the /tmp directory and it is slow.
    """
    out_path = Path(tmp_dir) / f"{file_path.stem}.{target_format}"
    logger.debug(f"Converting {file_path} to {target_format=} at: {out_path}")
    command = [
        "soffice",
        f"-env:UserInstallation=file:///tmp/{uuid4().hex}",
        "--headless",
        "--convert-to",
        target_format,
        "--outdir",
        str(tmp_dir),
        str(file_path),
    ]
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        _, stderr = process.communicate(timeout=timeout)
    except FileNotFoundError as e:
        raise FileNotFoundError("LibreOffice is not installed") from e

    if process.returncode != 0:
        logger.error(stderr.decode().strip())
        raise RuntimeError(
            f"LibreOffice failed to convert {file_path} to {target_format}"
        )

    return out_path
