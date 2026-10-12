"""Pure-logic tests for the tabular emitter (no DB): record dedupe, edge routing, role history."""

from datetime import UTC, datetime

from pytabular.records import SelectorValue, SlotRecord

from cipher.orchestration.extract_tables import _EdgeAgg, _edges, _mentions, _Seen, sheet_key
from cipher.schemas.graph.ontology import EntityType, RelationshipType, SelectorType
from cipher.schemas.ingestion.table_mapping import EdgeBinding

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _person(slot: str, name: str, iban: str) -> SlotRecord:
    return SlotRecord(
        slot=slot,
        entity_type=EntityType.PERSON,
        name=name,
        selectors=(SelectorValue(selector_type=SelectorType.IBAN, raw=iban, normalized=iban),),
        surface=(("name", name),),
    )


def test_sheet_key_is_field_path_safe():
    """Dots and spaces would break the `table.<sheet>.<slot>` prefix."""
    assert sheet_key(None) == "main"
    assert sheet_key("Q1 2024.final") == "Q1_2024_final"


def test_role_history_keeps_every_role_newest_last():
    """A person can hold several roles over time: all kept, the newest is `role`."""
    agg = _EdgeAgg()
    agg.observe(datetime(2019, 1, 1, tzinfo=UTC), {"role": "Engineer"})
    agg.observe(datetime(2022, 6, 1, tzinfo=UTC), {"role": "Chief engineer"})
    agg.observe(datetime(2019, 3, 1, tzinfo=UTC), {"role": "Engineer"})
    out = agg.as_attributes()
    assert out["role"] == "Chief engineer"
    assert [r["role"] for r in out["roles"]] == ["Engineer", "Chief engineer"]
    assert out["roles"][0]["rows"] == 2 and out["rows"] == 3


def test_amounts_are_totalled():
    agg = _EdgeAgg()
    agg.observe(None, {"amount": "100,50", "currency": "RUB"})
    agg.observe(None, {"amount": "1 000", "currency": "RUB"})
    assert agg.as_attributes()["amount_total"] == 1100.5


def test_comms_edges_between_selectors_go_to_entities_others_to_mentions():
    """`paid` between two IBAN-carrying slots aggregates onto the selector entities; `employed_by` stays a mention edge."""
    sender, receiver = _person("sender", "Ivan", "DE1"), _person("receiver", "Anna", "GB2")
    seen = {sender.key(): _Seen(record=sender, first_row=1), receiver.key(): _Seen(record=receiver, first_row=1)}
    selector_ids = {(SelectorType.IBAN, "DE1"): "e-de1", (SelectorType.IBAN, "GB2"): "e-gb2"}
    mentions, _ = _mentions(
        dataset_id="d",
        file_id="f",
        field_prefix="table.main.",
        sheet=None,
        seen=seen,
        selector_ids=selector_ids,
        now=NOW,
    )
    assert {m["field_path"] for m in mentions} == {"table.main.sender", "table.main.receiver"}
    assert all(set(m) == set(mentions[0]) for m in mentions)  # one column set for the bulk insert

    edges = [
        EdgeBinding(src_slot="sender", dst_slot="receiver", relationship_type=RelationshipType.PAID.value),
        EdgeBinding(src_slot="sender", dst_slot="receiver", relationship_type=RelationshipType.EMPLOYED_BY.value),
    ]
    paid, employed = _EdgeAgg(), _EdgeAgg()
    for _ in range(3):
        paid.observe(datetime(2024, 1, 5, tzinfo=UTC), {})
    employed.observe(None, {"role": "Accountant"})
    entity_edges, mention_edges = _edges(
        dataset_id="d",
        file_id="f",
        edges=edges,
        aggs={(0, sender.key(), receiver.key()): paid, (1, sender.key(), receiver.key()): employed},
        seen=seen,
        now=NOW,
    )
    assert [(e["src_entity_id"], e["dst_entity_id"], e["weight"]) for e in entity_edges] == [("e-de1", "e-gb2", 3.0)]
    assert [m["relationship_type"] for m in mention_edges] == [RelationshipType.EMPLOYED_BY]
    assert mention_edges[0]["attributes"]["role"] == "Accountant"
