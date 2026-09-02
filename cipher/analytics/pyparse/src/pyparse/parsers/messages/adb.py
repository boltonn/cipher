"""Parser for Android SMS and MMS messages via ADB, writing output to parquet."""

import hashlib
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import phonenumbers
from loguru import logger

from cipher.schemas.content.message import MessageBase, MessageStatus, PhoneNumberType

# These schemas must be defined in your environment
from cipher.schemas.ingestion.file import FileBase
from cipher.utils.io import HashType, compute_hash

SMS_TYPE_MAP = {
    "1": MessageStatus.INBOX,
    "2": MessageStatus.SENT,
    "3": MessageStatus.DRAFT,
    "4": MessageStatus.OUTBOX,
    "5": MessageStatus.FAILED,
    "6": MessageStatus.QUEUED,
}

MMS_MSG_BOX_MAP = {
    "1": MessageStatus.INBOX,
    "2": MessageStatus.SENT,
    "3": MessageStatus.DRAFT,
    "4": MessageStatus.OUTBOX,
}

MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/3gpp": ".3gp",
    "video/mp4": ".mp4",
    "audio/amr": ".amr",
    "audio/mpeg": ".mp3",
    "application/smil": ".smil",
}


def run_adb_cmd(args: list[str], check: bool = True) -> str:
    """Run an ADB command and return the stripped stdout string."""
    try:
        result = subprocess.run(
            ["adb", *args], capture_output=True, text=True, check=check
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"ADB Error: {e.stderr}")
        raise


def pull_device_data(outdir: Path, pull_media: bool = True) -> str:
    """Pull SMS/MMS content dumps and media files from a connected Android device."""
    outdir.mkdir(parents=True, exist_ok=True)

    uris = {
        "sms_dump.txt": "content://sms/",
        "mms_dump.txt": "content://mms/",
        "mms_addr_dump.txt": "content://mms/addr",
        "mms_parts_dump.txt": "content://mms/part",
    }

    for filename, uri in uris.items():
        logger.info(f"Querying {uri}...")
        with (outdir / filename).open("w", encoding="utf-8") as f:
            subprocess.run(
                ["adb", "shell", "content", "query", "--uri", uri], stdout=f, check=True
            )

    if pull_media:
        media_dir = outdir / "media"
        media_dir.mkdir(exist_ok=True)
        logger.info("Pulling MMS media files from telephony provider...")
        subprocess.run(
            [
                "adb",
                "pull",
                "/data/data/com.android.providers.telephony/app_parts/.",
                str(media_dir),
            ],
            check=False,
        )

    device_id = get_device_id()
    (outdir / "device_id.txt").write_text(device_id)
    return device_id


def get_device_id() -> str:
    """Retrieve a unique identifier based on device model and serial number."""
    serial = run_adb_cmd(["shell", "getprop", "ro.serialno"])
    model = run_adb_cmd(["shell", "getprop", "ro.product.model"])
    return f"{model}_{serial}".replace(" ", "_")


def normalize_phone_number(
    phone: str, default_region: str = "US"
) -> tuple[str, PhoneNumberType]:
    """Normalize phone numbers to E.164 format using phonenumbers library."""
    if not phone or phone.lower() in ("null", "unknown", "insert-address-token"):
        return ("unknown", PhoneNumberType.RAW_PHONE_NUMBER)
    try:
        parsed = phonenumbers.parse(phone, default_region)
        if phonenumbers.is_possible_number(parsed):
            return (
                phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                PhoneNumberType.ITU_E164,
            )
    except Exception:
        pass
    return (phone, PhoneNumberType.RAW_PHONE_NUMBER)


def generate_meaningful_hash(
    text: str | None, file_hash: str | None, participants: list[str], timestamp: str
) -> str:
    """Create a SHA256 hash for message deduplication based on content and metadata."""
    participants_sorted = "|".join(sorted(participants))
    content = file_hash or text or ""
    hash_input = f"{content}|{participants_sorted}|{timestamp}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def parse_content_dump(input_path: Path):
    """Parser that handles multi-line ADB rows and captures full message bodies."""
    if not input_path.exists():
        return

    # 1. Read the whole file and split by "Row: " to handle multi-line records
    content = input_path.read_text(encoding="utf-8")
    rows = re.split(r"\nRow: \d+ ", content)

    # 2. List of keys we expect to find in the ADB output
    # We use these as delimiters because ADB doesn't quote values consistently.
    known_keys = [
        "_id",
        "thread_id",
        "address",
        "person",
        "date",
        "date_sent",
        "protocol",
        "read",
        "status",
        "type",
        "reply_path_present",
        "subject",
        "body",
        "service_center",
        "locked",
        "sub_id",
        "error_code",
        "creator",
        "seen",
        "contains_otp",
    ]

    # Build a regex that finds any of these keys followed by an equals sign
    # e.g. (?:^| )(_id|thread_id|body)=
    key_regex = re.compile(r"(?:^| )(" + "|".join(known_keys) + r")=")

    for row_text in rows:
        row_text = row_text.strip()
        if not row_text:
            continue

        # Find all keys and their positions in this row
        matches = list(key_regex.finditer(row_text))
        record = {}

        for i in range(len(matches)):
            key = matches[i].group(1)
            start_val = matches[i].end()

            # The value ends where the next key starts, or at the end of the string
            end_val = matches[i + 1].start() if i + 1 < len(matches) else len(row_text)

            value = row_text[start_val:end_val].strip()

            # Clean up the trailing comma that ADB adds to values
            if value.endswith(","):
                value = value[:-1]

            # Strip quotes if ADB decided to add them
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]

            record[key] = value

        if record:
            yield record


def load_mms_addr_index(addr_dump: Path) -> dict[str, list[dict]]:
    """Map MMS message IDs to their corresponding address records (sender/recipients)."""
    index = defaultdict(list)
    for record in parse_content_dump(addr_dump):
        if mid := record.get("msg_id"):
            index[mid].append(record)
    return dict(index)


def load_mms_parts_index(parts_dump: Path) -> dict[str, list[dict]]:
    """Map MMS message IDs to their corresponding file/text parts."""
    index = defaultdict(list)
    for record in parse_content_dump(parts_dump):
        if mid := record.get("mid"):
            index[mid].append(record)
    return dict(index)


def parse_sms_record(device_phone: str, sms: dict, region: str) -> MessageBase | None:
    """Transform a raw SMS dictionary record into a validated MessageBase object."""
    body = sms.get("body")
    if not body:
        return None

    status = SMS_TYPE_MAP.get(sms.get("type", "1"), MessageStatus.INBOX)
    addr_raw = sms.get("address", "unknown")

    dev_n, dev_t = normalize_phone_number(device_phone, region)
    adr_n, adr_t = normalize_phone_number(addr_raw, region)

    sender, s_type = (adr_n, adr_t) if status == MessageStatus.INBOX else (dev_n, dev_t)
    recipient, r_type = (
        (dev_n, dev_t) if status == MessageStatus.INBOX else (adr_n, adr_t)
    )

    ts_ms = int(sms.get("date", 0))
    dt = datetime.fromtimestamp(ts_ms / 1000) if ts_ms else datetime.now()

    return MessageBase(
        message_id=f"sms_{sms.get('_id')}",
        sender=sender,
        sender_type=s_type,
        recipient=recipient,
        recipient_type=r_type,
        date_received=dt,
        text=body,
        conversation_id=sms.get("thread_id", "0"),
        message_status=status,
        meaningful_hash=generate_meaningful_hash(
            body, None, [sender, recipient], dt.isoformat()
        ),
        source_type="sms",
    )


def parse_mms_record(
    device_phone: str,
    device_id: str,
    mms: dict,
    addr_index: dict,
    parts_index: dict,
    media_dir: Path,
    region: str,
):
    """Assemble an MMS message and its attachments from multiple data indexes."""
    mid = mms.get("_id")
    addrs = addr_index.get(mid, [])
    # 151 is TO, 137 is FROM in Android MMS provider
    recipients = [a.get("address") for a in addrs if a.get("type") == "151"]
    if not recipients:
        return None

    dev_n, dev_t = normalize_phone_number(device_phone, region)
    rec_n, rec_t = normalize_phone_number(recipients[0], region)

    status = MMS_MSG_BOX_MAP.get(mms.get("msg_box", "1"), MessageStatus.INBOX)
    sender, s_type = (rec_n, rec_t) if status == MessageStatus.INBOX else (dev_n, dev_t)
    recipient, r_type = (
        (dev_n, dev_t) if status == MessageStatus.INBOX else (rec_n, rec_t)
    )

    ts_s = int(mms.get("date", 0))
    dt = datetime.fromtimestamp(ts_s) if ts_s else datetime.now()

    parts = parts_index.get(mid, [])
    body = (
        "\n".join(
            p.get("text", "") for p in parts if p.get("ct") == "text/plain"
        ).strip()
        or None
    )

    files = []
    for p in parts:
        mime = p.get("ct", "")
        if mime in ("text/plain", "application/smil") or not mime:
            continue

        part_id = p.get("_id")
        data_path = p.get("_data", "")
        src_file = (
            media_dir / Path(data_path).name
            if data_path
            else media_dir / f"PART_{part_id}"
        )

        if src_file.exists():
            ext = MIME_TO_EXT.get(mime, ".bin")
            final_file = media_dir / f"mms_{mid}_part_{part_id}{ext}"
            if not final_file.exists():
                src_file.rename(final_file)

            files.append(
                FileBase(
                    filename=final_file.name,
                    path=str(final_file.resolve()),
                    uri=f"content://mms/part/{part_id}",
                    device=device_id,
                    mime_type=mime,
                    sha256=compute_hash(final_file, HashType.SHA256),
                    size=final_file.stat().st_size,
                    date_created=dt,
                )
            )

    msg = MessageBase(
        message_id=f"mms_{mid}",
        sender=sender,
        sender_type=s_type,
        recipient=recipient,
        recipient_type=r_type,
        date_received=dt,
        text=body,
        conversation_id=mms.get("thread_id", "0"),
        message_status=status,
        meaningful_hash=generate_meaningful_hash(
            body,
            files[0].sha256 if files else None,
            [sender, recipient],
            dt.isoformat(),
        ),
        source_type="mms",
    )
    return msg, files


def _messages_to_parquet(messages: list[MessageBase], path: Path) -> None:
    """Write a list of MessageBase objects to a Parquet file."""
    if messages:
        pd.DataFrame([m.model_dump() for m in messages]).to_parquet(path)


def _files_to_parquet(files: list[FileBase], path: Path) -> None:
    """Write a list of FileBase objects to a Parquet file."""
    if files:
        pd.DataFrame([f.model_dump() for f in files]).to_parquet(path)
