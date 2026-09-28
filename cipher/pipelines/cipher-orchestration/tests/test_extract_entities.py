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
    assert m.normalized_value == "acme corp"
    assert (m.start_offset, m.end_offset) == (10, 19)
    assert m.extractor == "gliner"


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
        _build_extractor(
            "gliner", model=None, gliner_model_dir=None, glirel_model_dir=None, nerd_model_dir=None, threshold=0.5
        )
    with pytest.raises(ValueError, match="nerd-model-dir"):
        _build_extractor(
            "nerd", model=None, gliner_model_dir=None, glirel_model_dir=None, nerd_model_dir=None, threshold=0.5
        )
    with pytest.raises(ValueError, match="Unknown"):
        _build_extractor(
            "bogus", model=None, gliner_model_dir=None, glirel_model_dir=None, nerd_model_dir=None, threshold=0.5
        )


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
