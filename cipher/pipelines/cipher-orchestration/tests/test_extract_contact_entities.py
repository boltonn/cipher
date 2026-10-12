"""Pure-logic tests for the Contact -> mention producer (no DB)."""

from types import SimpleNamespace

from cipher.orchestration.extract_contact_entities import _contact_name, _name_mention
from cipher.schemas.graph.mention import MentionedType
from cipher.schemas.graph.ontology import EntityType


def test_contact_name_prefers_full_name():
    """full_name wins; else first + last."""
    assert (
        _contact_name(SimpleNamespace(full_name="Nick Bolton", first_name="Nick", last_name="Bolton")) == "Nick Bolton"
    )
    assert _contact_name(SimpleNamespace(full_name=None, first_name="Nick", last_name="Bolton")) == "Nick Bolton"
    assert _contact_name(SimpleNamespace(full_name=None, first_name="Nick", last_name=None)) == "Nick"
    assert _contact_name(SimpleNamespace(full_name=None, first_name=None, last_name=None)) == ""


def test_name_mention_is_structured_field_with_shared_field_path():
    """The name mention shares `field_path` with the contact's selector mentions."""
    m = _name_mention(dataset_id="d", contact_id="c1", file_id="f1", name="Nick Bolton", entity_type=EntityType.PERSON)
    assert m.mentioned_type is MentionedType.STRUCTURED_FIELD
    assert m.mentioned_id == "c1"
    assert m.field_path == "contact.name"
    assert m.entity_type is EntityType.PERSON
    assert m.entity_attribute == "name"
    assert m.normalized_value == "nick bolton"
    assert m.entity_id is None  # unresolved -> goes through resolve-entities
    assert m.extractor == "contacts"


def test_org_name_mention_is_typed_organization():
    """A vCard ORG becomes an organization name mention (paired with a member_of relation)."""
    m = _name_mention(
        dataset_id="d", contact_id="c1", file_id=None, name="Acme Corp", entity_type=EntityType.ORGANIZATION
    )
    assert m.entity_type is EntityType.ORGANIZATION
    assert m.normalized_value == "acme"  # legal form is not part of the name key
