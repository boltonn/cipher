"""`pyarchive extract <file>`: stand-alone extraction into an output store, one JSON line per member.

`pyarchive sandbox`: which of 7zz's sandbox layers this machine applies.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from cipher.utils.output import OutputStore
from pyarchive.extract import extract

app = typer.Typer(no_args_is_help=True)


@app.command("extract")
def extract_cmd(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Archive to extract")],
    output_uri: Annotated[str, typer.Option(help="Directory or s3://bucket/prefix to write members to")] = (
        "~/data/cipher/output"
    ),
    passwords_file: Annotated[Path | None, typer.Option(help="Passwords to try, one per line")] = None,
) -> None:
    """Type the archive with filetyper, then stream its members into the output store."""
    from filetyper.models.main import FileTyper

    info = FileTyper().get_file_info(path)
    compression = info["compression"].encoding if info["compression"] else None
    passwords = [line for line in passwords_file.read_text().splitlines() if line] if passwords_file else []
    store = OutputStore(output_uri)
    for member in extract(path, info["filetype"], store, compression=compression, passwords=passwords):
        typer.echo(member.model_dump_json(by_alias=True, exclude_none=True))


@app.command("sandbox")
def sandbox_cmd() -> None:
    """Report which sandbox layers 7zz would run under here, and that 7zz still runs inside it (exit 1 if not)."""
    from pyarchive import jail
    from pyarchive.backends.sevenzip import find_sevenzip

    binary = find_sevenzip()
    command = [str(binary), "i"] if binary else [shutil.which("true") or "/bin/true"]
    typer.echo(f"7zz: {binary or 'not found (7z / rar / iso unsupported; layers checked with true)'}")
    with tempfile.TemporaryDirectory() as scratch:
        report_read, report_write = os.pipe()
        wrapped = jail.jail_command(
            command,
            read=[],
            execute=[command[0]],
            write=[scratch],
            max_file_bytes=1 << 30,
            max_memory_bytes=4 << 30,
            report_fd=report_write,
        )
        process = subprocess.Popen(  # noqa: S603
            wrapped, pass_fds=(report_write,), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=scratch
        )
        os.close(report_write)
        with os.fdopen(report_read) as report:
            layers = json.loads(report.read() or "{}")
        _, err = process.communicate()
    for layer in jail.LAYERS:
        outcome = layers.get(layer, "no report")
        name, lost, fix = jail.PLAIN[layer]
        typer.echo(f"{name:19} {'ok' if outcome == 'ok' else 'NO (' + outcome + ')'}")
        if outcome != "ok":
            typer.echo(f"{'':19} without it: {lost}\n{'':19} to fix: {fix}")
    runs = process.returncode == 0 or binary is None  # `true` is dynamically linked, so the jail may refuse it
    detail = "" if runs else f" (exit {process.returncode}: {err.decode(errors='replace').strip()[-200:]})"
    if binary is not None:
        typer.echo(f"{'7-Zip runs in it':19} {'ok' if runs else 'NO' + detail}")
    if not runs:
        typer.echo(f"{'':19} the sandbox blocks 7-Zip itself here: extract with --sandbox off")
    raise typer.Exit(0 if runs and all(layers.get(layer) == "ok" for layer in jail.LAYERS) else 1)


@app.callback()
def main() -> None:
    """Archive extraction."""
