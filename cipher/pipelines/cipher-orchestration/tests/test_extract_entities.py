"""Pure-logic tests for entity + relation span mapping (no DB, no models)."""

import pytest

from cipher.datastores.postgres.repositories.mention_relationship import _legal_endpoints
from cipher.orchestration.extract_entities import (
    MentionRowRef,
    _build_extractor,
    _relations_for_file,
    _to_mention,
)
from cipher.schemas.graph.ontology import EntityType, RelationshipType
from cipher.schemas.graph.spans import EntitySpan, RelationSpan


def test_to_mention_maps_org_span():
    span = EntitySpan(surface_text="Acme Corp", label="organization", start_offset=10, end_offset=19, score=0.9)
    m = _to_mention(
        span, dataset_id="d", file_id="f", extracted_id="x", content="x" * 100, extractor="gliner", model="g"
    )
    assert m is not None
    assert m.entity_type == EntityType.ORGANIZATION
    assert m.entity_attribute == "name"
    assert m.normalized_value == "acme"  # legal form is not part of the name key
    assert (m.start_offset, m.end_offset) == (10, 19)
    assert m.extractor == "gliner"


@pytest.mark.parametrize("written", ["Nick Bolton's", '"Nick Bolton"', "«Nick Bolton»", "'Nick Bolton’s'"])
def test_to_mention_trims_quotes_and_possessive_into_one_name_group(written):
    content = f"met {written} today"
    span = EntitySpan(surface_text=written, label="person", start_offset=4, end_offset=4 + len(written), score=0.9)
    m = _to_mention(span, dataset_id="d", file_id="f", extracted_id="x", content=content, extractor="g", model="g")
    assert m is not None
    assert m.surface_text == "Nick Bolton" == content[m.start_offset : m.end_offset]
    assert m.normalized_value == "nick bolton"


def test_to_mention_skips_selector_and_unknown_labels():
    assert (
        _to_mention(
            EntitySpan(surface_text="+1 555 0100", label="phone number", start_offset=0, end_offset=11),
            dataset_id="d",
            file_id="f",
            extracted_id="x",
            content="+1 555 0100",
            extractor="llm",
            model=None,
        )
        is None
    )
    assert (
        _to_mention(
            EntitySpan(surface_text="widget", label="product", start_offset=0, end_offset=6),
            dataset_id="d",
            file_id="f",
            extracted_id="x",
            content="widget",
            extractor="llm",
            model=None,
        )
        is None
    )


def test_relations_map_to_mention_rows_by_offset():
    refs = {10: MentionRowRef("head", 10, 14), 40: MentionRowRef("tail", 40, 48)}
    rels = [
        RelationSpan(label="employed by", head_text="John", tail_text="Acme", head_start=10, tail_start=40, score=0.7)
    ]
    rows = _relations_for_file(rels, refs, dataset_id="d", file_id="f", content="y" * 100, extractor="llm", model="m")
    assert len(rows) == 1
    assert (rows[0].src_mention_id, rows[0].dst_mention_id) == ("head", "tail")
    assert rows[0].relationship_type == RelationshipType.EMPLOYED_BY
    assert rows[0].confidence == pytest.approx(0.7)


def test_relations_dropped_when_endpoint_missing_or_label_unknown():
    refs = {10: MentionRowRef("head", 10, 14)}
    assert (
        _relations_for_file(
            [RelationSpan(label="employed by", head_text="a", tail_text="b", head_start=10, tail_start=99, score=0.5)],
            refs,
            dataset_id="d",
            file_id="f",
            content="z" * 100,
            extractor="llm",
            model="m",
        )
        == []
    )
    refs2 = {10: MentionRowRef("head", 10, 14), 40: MentionRowRef("tail", 40, 48)}
    assert (
        _relations_for_file(
            [RelationSpan(label="frobnicates", head_text="a", tail_text="b", head_start=10, tail_start=40, score=0.5)],
            refs2,
            dataset_id="d",
            file_id="f",
            content="z" * 100,
            extractor="llm",
            model="m",
        )
        == []
    )


def test_build_extractor_requires_model_dirs():
    with pytest.raises(ValueError, match="gliner-model-dir"):
        _build_extractor("gliner", model=None, gliner_model_dir=None, nerd_model_dir=None, threshold=0.5)
    with pytest.raises(ValueError, match="nerd-model-dir"):
        _build_extractor("nerd", model=None, gliner_model_dir=None, nerd_model_dir=None, threshold=0.5)
    with pytest.raises(ValueError, match="Unknown"):
        _build_extractor("bogus", model=None, gliner_model_dir=None, nerd_model_dir=None, threshold=0.5)


def test_legal_endpoints_direction_and_symmetry():
    # directed, correct way round
    assert _legal_endpoints(RelationshipType.EMPLOYED_BY, "p", "o", EntityType.PERSON, EntityType.ORGANIZATION) == (
        "p",
        "o",
    )
    # directed, wrong way round -> rejected (not symmetric)
    assert _legal_endpoints(RelationshipType.EMPLOYED_BY, "o", "p", EntityType.ORGANIZATION, EntityType.PERSON) is None
    # symmetric -> accepted regardless of order
    assert _legal_endpoints(RelationshipType.FAMILY_OF, "a", "b", EntityType.PERSON, EntityType.PERSON) == ("a", "b")
    # endpoints not permitted for the type at all
    assert _legal_endpoints(RelationshipType.FAMILY_OF, "a", "b", EntityType.PERSON, EntityType.ORGANIZATION) is None


def _old(start, end, value, entity_id, entity_type="person"):
    from types import SimpleNamespace

    return SimpleNamespace(
        start_offset=start, end_offset=end, normalized_value=value, entity_id=entity_id, entity_type=entity_type
    )


def _new(start, end, value, entity_type="person"):
    from cipher.schemas.graph.mention import MentionCreate

    return MentionCreate(
        dataset_id="d",
        mentioned_type="EXTRACTED_TEXT",
        mentioned_id="x",
        surface_text=value,
        entity_type=entity_type,
        entity_attribute="name",
        normalized_value=value,
        start_offset=start,
        end_offset=end,
    )


def test_rescan_keeps_entity_of_the_same_span():
    """A span re-found at the same offsets keeps its entity."""
    from cipher.orchestration.extract_entities import entity_inheritance

    entity_for = entity_inheritance([_old(10, 21, "megan flick", "megan")], {})
    assert entity_for(_new(10, 21, "megan flick")) == "megan"


def test_rescan_repairs_a_fragment_to_the_names_entity():
    """`n Flick` (unresolved) and `Megan Flick` (resolved) become one whole `Megan Flick` on that entity."""
    from cipher.orchestration.extract_entities import entity_inheritance

    old = [_old(10, 21, "megan flick", "megan"), _old(54, 61, "n flick", None), _old(50, 61, "megan flick", "megan")]
    entity_for = entity_inheritance(old, {})
    assert entity_for(_new(50, 61, "megan flick")) == "megan"
    assert entity_for(_new(90, 101, "megan flick")) == "megan"  # same name elsewhere in the text


def test_rescan_falls_back_to_dataset_wide_unambiguous_name():
    """A name new to this text takes the one entity it resolves to dataset-wide; type must match."""
    from cipher.orchestration.extract_entities import entity_inheritance

    entity_for = entity_inheritance([], {("person", "liz hughes"): "liz"})
    assert entity_for(_new(0, 10, "liz hughes")) == "liz"
    assert entity_for(_new(0, 10, "liz hughes", entity_type="organization")) is None
    assert entity_for(_new(0, 5, "dolce")) is None


def test_address_stops_at_contact_lines():
    """An address span ends before the phone / email lines under it."""
    from cipher.orchestration.extract_entities import address_length

    surface = "3141 Chestnut Street\n\nPhiladelphia, PA 19104\n\nTel: 215.895.2372"
    assert surface[: address_length(surface)] == "3141 Chestnut Street\n\nPhiladelphia, PA 19104"
    assert address_length("Unter den Linden 77\n10117 Berlin") == len("Unter den Linden 77\n10117 Berlin")
