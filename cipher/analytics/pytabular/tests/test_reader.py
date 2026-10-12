import csv
import json
from pathlib import Path

import pytest
from pytabular.header import detect_header
from pytabular.reader import open_table, sniff_encoding

from cipher.schemas.ingestion.table_mapping import TableFormat

ROWS = [["Иванов Иван", "+7 916 123-45-67", "ivan@mail.ru"], ["Петрова Анна", "+7 926 765-43-21", "anna@ya.ru"]] * 30


def write_csv(path: Path, rows: list[list[str]], *, encoding: str = "utf-8", delimiter: str = ",") -> Path:
    with path.open("w", encoding=encoding, newline="") as handle:
        csv.writer(handle, delimiter=delimiter).writerows(rows)
    return path


@pytest.mark.parametrize("encoding", ["utf-8", "cp1251", "utf-16"])
def test_encodings_round_trip(tmp_path: Path, encoding: str):
    path = write_csv(tmp_path / "t.csv", [["ФИО", "Телефон", "Email"], *ROWS], encoding=encoding, delimiter=";")
    source = open_table(path)
    sample = source.sample(head=10, spread=10)
    assert source.delimiter == ";"
    assert sample.head[0] == ["ФИО", "Телефон", "Email"]
    assert sample.head[1][0] == "Иванов Иван"


def test_sniff_encoding_tolerates_cut_multibyte():
    raw = "Иванов".encode()[:-1]
    assert sniff_encoding(raw) == "utf-8"


def test_header_first_row():
    guess = detect_header([["Name", "Phone", "Email"], *ROWS])
    assert guess.header_rows == [0]
    assert guess.names == ["Name", "Phone", "Email"]


def test_header_below_title_rows():
    rows = [["Subscriber export"], [], ["Exported 2024-03-01"], ["ФИО", "Телефон", "Email"], *ROWS]
    guess = detect_header(rows)
    assert guess.header_rows == [3]
    assert guess.data_start_row == 4


def test_no_header():
    guess = detect_header(ROWS)
    assert guess.header_rows == []
    assert guess.names == ["column_1", "column_2", "column_3"]


def test_two_row_header():
    rows = [["Sender", "", "Receiver", ""], ["Name", "Phone", "Name", "Phone"], *[r + r[:1] for r in ROWS]]
    guess = detect_header(rows)
    assert guess.header_rows == [0, 1]
    assert guess.names == ["Sender Name", "Sender Phone", "Receiver Name", "Receiver Phone"]


def test_jsonl_flattens_nested(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps({"name": "Ivan", "contact": {"phone": "+79161234567"}}) for _ in range(5)))
    source = open_table(path)
    sample = source.sample(head=3, spread=5)
    assert source.format is TableFormat.JSONL
    assert sample.names == ["name", "contact.phone"]
    assert len(sample.head) + len(sample.spread) == 5


def test_large_csv_is_seek_sampled(tmp_path: Path):
    path = tmp_path / "big.csv"
    line = "Иванов Иван,+7 916 123-45-67,ivan@mail.ru\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write("name,phone,email\n")
        chunk = line * 10_000
        while handle.tell() < 70 << 20:
            handle.write(chunk)
    sample = open_table(path).sample(head=100, spread=500)
    assert len(sample.head) == 100
    assert 400 <= len(sample.spread) <= 500
    assert sample.rows_estimate and sample.rows_estimate > 1_000_000
