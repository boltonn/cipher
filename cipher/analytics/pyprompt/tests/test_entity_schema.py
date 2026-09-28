"""The entities `response_format` is enum-locked to the ontology vocabulary."""

import pytest
from pydantic import ValidationError
from pyprompt.schemas import build_entity_output_model

from cipher.schemas.graph.ontology import default_ner_labels, default_relation_labels

_LABELS = tuple(default_ner_labels())
_RELS = tuple(default_relation_labels())


def test_label_fields_become_enums_in_json_schema():
    """Each `label` is a string enum of exactly the provided vocabulary."""
    model = build_entity_output_model(_LABELS, _RELS)
    defs = model.model_json_schema()["$defs"]
    assert set(defs["LlmEntityStrict"]["properties"]["label"]["enum"]) == set(_LABELS)
    assert set(defs["LlmRelationStrict"]["properties"]["label"]["enum"]) == set(_RELS)


def test_in_vocabulary_labels_validate():
    """A signature-shaped payload (person, org, employed by) is accepted."""
    model = build_entity_output_model(_LABELS, _RELS)
    out = model(
        entities=[
            {"surface_text": "Jane Smith", "label": "person"},
            {"surface_text": "Acme Corp", "label": "organization"},
        ],
        relations=[{"head_text": "Jane Smith", "tail_text": "Acme Corp", "label": "employed by"}],
    )
    assert out.entities[1].label == "organization"
    assert out.relations[0].label == "employed by"


def test_out_of_vocabulary_label_is_rejected():
    """A paraphrased entity or relation label fails validation, not silently drops later."""
    model = build_entity_output_model(_LABELS, _RELS)
    with pytest.raises(ValidationError):
        model(entities=[{"surface_text": "x", "label": "widget"}])
    with pytest.raises(ValidationError):
        model(relations=[{"head_text": "a", "tail_text": "b", "label": "works at"}])


def test_model_is_cached_per_vocabulary():
    """Same label set -> same model object (built once)."""
    assert build_entity_output_model(_LABELS, _RELS) is build_entity_output_model(_LABELS, _RELS)
