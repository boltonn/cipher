import json


def flatten_json_records(data: bytes, jsonl: bool) -> list[list[str]] | None:
    """Flatten JSON array-of-objects or JSONL/NDJSON bytes into a cells table.

    Column order follows first-seen key order across records; a record
    missing a given key renders as an empty string for that column. Returns
    None when there are no object records to tabulate (xberg already
    extracts these filetypes' raw text, so this is only reached when a
    structured table view is wanted on top of that).
    """
    if jsonl:
        records = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    else:
        parsed = json.loads(data.decode("utf-8"))
        records = parsed if isinstance(parsed, list) else [parsed]

    records = [record for record in records if isinstance(record, dict)]
    if not records:
        return None

    columns: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                columns.append(key)

    rows = [[_stringify(record.get(column)) for column in columns] for record in records]
    return [columns, *rows]


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)
