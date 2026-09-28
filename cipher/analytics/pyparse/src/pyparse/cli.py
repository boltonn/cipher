"""CLI for pulling Android SMS/MMS from a device and parsing dumps into parquet."""

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from loguru import logger
from rich.pretty import pprint

from pyparse.parsers.messages import adb

app = typer.Typer(help="Pull and parse Android SMS/MMS messages.")


@app.command("pull")
def cmd_pull(
    outdir: Annotated[Path, typer.Argument(help="Directory to write all dump files and media")],
    media: Annotated[bool, typer.Option("--media/--no-media", help="Also pull MMS media files")] = True,
) -> None:
    """Command to trigger the ADB extraction process for messages and media."""
    try:
        device_id = adb.pull_device_data(outdir, pull_media=media)
        typer.echo(f"Successfully pulled data for device: {device_id}")
    except Exception as e:
        logger.error(f"Pull failed: {e}")


@app.command()
def preview(
    path: Annotated[Path, typer.Argument(help="Path to the parquet file to preview")],
    col: Annotated[str, typer.Option("--col", help="Column to show value counts for")] = None,
) -> None:
    """Command to preview the contents of a Parquet file."""
    if not path.exists():
        typer.echo(f"Error: File {path} does not exist.")
        raise typer.Exit(1)
    df = pd.read_parquet(path)
    pprint(df.columns)
    print(df.head())
    if col:
        pprint(df[col].head(n=20))


@app.command("parse")
def cmd_parse(
    dump_dir: Annotated[Path, typer.Argument(help="Directory containing the pulled .txt dumps")],
    device_phone: Annotated[str, typer.Option(help="Device phone number e.g. +12125550100")],
    region: Annotated[str, typer.Option(help="Default region for phone parsing")] = "US",
) -> None:
    """Command to parse raw text dumps into structured Parquet files offline."""
    if not dump_dir.exists():
        typer.echo(f"Error: Directory {dump_dir} does not exist.")
        raise typer.Exit(1)

    # Initialize MMS indices using the functions now included in adb
    addr_index = adb.load_mms_addr_index(dump_dir / "mms_addr_dump.txt")
    parts_index = adb.load_mms_parts_index(dump_dir / "mms_parts_dump.txt")

    device_id_path = dump_dir / "device_id.txt"
    device_id = device_id_path.read_text().strip() if device_id_path.exists() else "unknown"

    sms_msgs = []
    for rec in adb.parse_content_dump(dump_dir / "sms_dump.txt"):
        msg = adb.parse_sms_record(device_phone, rec, region)
        if msg:
            sms_msgs.append(msg)

    mms_msgs = []
    mms_files = []
    for rec in adb.parse_content_dump(dump_dir / "mms_dump.txt"):
        res = adb.parse_mms_record(
            device_phone,
            device_id,
            rec,
            addr_index,
            parts_index,
            dump_dir / "media",
            region,
        )
        if res:
            mms_msgs.append(res[0])
            mms_files.extend(res[1])

    adb._messages_to_parquet(sms_msgs, dump_dir / "sms_messages.parquet")
    adb._messages_to_parquet(mms_msgs, dump_dir / "mms_messages.parquet")
    adb._files_to_parquet(mms_files, dump_dir / "mms_files.parquet")

    typer.echo(f"Parsing complete. Found {len(sms_msgs)} SMS, {len(mms_msgs)} MMS, and {len(mms_files)} files.")


if __name__ == "__main__":
    app()
