from pathlib import Path

import pytest
from pytabular.build import build_detectors
from pytabular.decide import ProfileConfig, profile_table
from pytabular.detectors.header_lexicon import score_header
from pytabular.detectors.validators import cell_checks, hit_rate, parse_date
from pytabular.evaluate import LabelledTable, evaluate
from pytabular.synth import make_tables

from cipher.schemas.graph.ontology import EntityType, SelectorType
from cipher.schemas.ingestion.table_mapping import EdgeBinding, EntitySlot, MappingDecisionSource

DETECTORS = build_detectors(["header", "validators"])


@pytest.mark.parametrize(
    ("header", "field", "role"),
    [
        ("Телефон отправителя", "selector.phone", "sender"),
        ("receiver_phone_number", "selector.phone", "receiver"),
        ("发送方姓名", "person.full_name", "sender"),
        ("CallerNumber", "selector.phone", "sender"),
        ("called_number", "selector.phone", "receiver"),
        ("Дата рождения", "person.date_of_birth", None),
        ("E-mail", "selector.email", None),
    ],
)
def test_header_field_and_role(header: str, field: str, role: str | None):
    scores = score_header(header)
    assert max(scores.scores, key=scores.scores.__getitem__) == field
    assert scores.role == role


def test_cell_checks():
    checks = cell_checks("RU")
    assert checks["selector.phone"]("+7 916 123-45-67")
    assert checks["selector.email"]("ivan@mail.ru")
    assert checks["selector.national_id"]("7707083893")
    assert not checks["selector.national_id"]("1577")
    assert checks["location.coordinate"]("55.7558, 37.6173")
    assert checks["location.longitude"]("37°37′E")
    assert checks["person.full_name"]("王伟")
    assert checks["person.full_name"]("IVAN PETROV")
    assert not checks["organization.name"]("IVAN PETROV")
    assert checks["organization.name"]('ООО "Ромашка"')


@pytest.mark.parametrize(
    ("value", "year", "has_time"),
    [
        ("2024-01-05", 2024, False),
        ("05.01.2024 13:45", 2024, True),
        ("12/31/1999", 1999, False),
        ("2024年1月5日", 2024, False),
    ],
)
def test_parse_date(value: str, year: int, has_time: bool):
    parsed, timed = parse_date(value)
    assert parsed is not None and parsed.year == year and timed is has_time


def test_hit_rate_reports_failing_cells():
    rate, failing = hit_rate("selector.email", ["a@b.com", "c@d.org", "not an email"], region=None)
    assert rate == pytest.approx(2 / 3)
    assert failing == ["not an email"]


def _write(path: Path, header: str, rows: list[str]) -> Path:
    path.write_text("\n".join([header, *rows]), encoding="utf-8")
    return path


def test_transfer_table_slots_and_edges(tmp_path: Path):
    rows = [
        f"Иванов Иван,DE89370400440532013000,Петрова Анна,GB82WEST12345698765432,{100 + i}.50,RUB,2024-01-{1 + i % 28:02d}"
        for i in range(60)
    ]
    path = _write(
        tmp_path / "t.csv", "ФИО отправителя,IBAN отправителя,ФИО получателя,IBAN получателя,Сумма,Валюта,Дата", rows
    )
    mapping = profile_table(path, detectors=DETECTORS)[0]
    types = [c.field_type for c in mapping.columns]
    assert types == [
        "person.full_name",
        "selector.iban",
        "person.full_name",
        "selector.iban",
        "edge.amount",
        "edge.currency",
        "time.date",
    ]
    slots = {s.name: s for s in mapping.slots}
    assert slots["sender"].columns == [0, 1] and slots["receiver"].columns == [2, 3]
    assert mapping.columns[1].selector_type is SelectorType.IBAN
    [edge] = mapping.edges
    assert (edge.src_slot, edge.dst_slot, edge.relationship_type) == ("sender", "receiver", "paid")
    assert not edge.is_proposed_verb and edge.date_column == 6 and edge.attribute_columns == [4, 5]


def test_user_edits_are_locked_and_rest_re_evaluated(tmp_path: Path):
    rows = [f"Ivan Petrov,55.{1000 + i},37.{2000 + i},x{i}" for i in range(60)]
    path = _write(tmp_path / "t.csv", "name,col_a,col_b,code", rows)
    first = profile_table(path, detectors=DETECTORS)[0]

    edited = first.model_copy(deep=True)
    edited.columns[1].field_type = "location.latitude"
    edited.columns[1].decision_source = MappingDecisionSource.USER
    edited.columns[3].field_type = "selector.username"
    edited.columns[3].decision_source = MappingDecisionSource.USER
    edited.slots = [
        EntitySlot(
            name="handle", entity_type=EntityType.SELECTOR, columns=[3], decision_source=MappingDecisionSource.USER
        )
    ]
    edited.edges = [
        EdgeBinding(
            src_slot="person",
            dst_slot="handle",
            relationship_type="has_selector",
            decision_source=MappingDecisionSource.USER,
        )
    ]

    second = profile_table(path, detectors=DETECTORS, locked=[edited])[0]
    assert second.columns[1].field_type == "location.latitude"
    assert second.columns[1].decision_source is MappingDecisionSource.USER
    assert second.columns[1].hit_rate == 1.0
    assert second.columns[2].field_type == "location.longitude"
    slots = {s.name: s for s in second.slots}
    assert slots["handle"].columns == [3] and slots["handle"].decision_source is MappingDecisionSource.USER
    assert slots["location"].columns == [1, 2]
    assert any(
        e.relationship_type == "has_selector" and e.decision_source is MappingDecisionSource.USER for e in second.edges
    )


def test_synthetic_accuracy_floor(tmp_path: Path):
    tables = [
        LabelledTable(path=t.path, labels=dict(enumerate(t.labels)))
        for t in make_tables(tmp_path, count=14, seed=3, rows=150)
    ]
    [result] = evaluate(tables, {"header,validators": DETECTORS}, config=ProfileConfig(cascade=False))
    assert result.accuracy >= 0.9
