from pathlib import Path
from typing import Any

from loguru import logger
from pyparse.parsers.contacts.vcard import parse_contacts
from rich.pretty import pprint

in_dir = Path.home() / "data" / "google" / "Takeout"
file_paths = sorted(in_dir.rglob("*.vcf"))

unique_fields = set()
for test_file in file_paths:
    contacts = parse_contacts(test_file)

    # pprint(contacts)

    # give me all the unique fields in the vcf files
    for record in contacts:
        contact: dict[str, Any] = record.model_dump()
        for key in contact:
            try:
                unique_fields.add(key)
            except Exception:
                logger.error(f"Error adding key: {key}")
            if key == "raw_header":
                for raw_key in contact[key]:
                    unique_fields.add(f"raw_header.{raw_key}")
pprint(sorted(unique_fields))
