"""Pure-logic tests for the resolve-entities sweep helpers (no DB)."""

from cipher.orchestration.entity_resolution import ScoredCandidate
from cipher.orchestration.resolve_entities import (
    _mention_scoring_input,
    _pick_display_name,
    _plan,
    _provenance_for_group,
)
from cipher.schemas.graph.entity_match import EntityMatchMethod
from cipher.schemas.graph.entity_resolution import DEFAULT_RESOLUTION_CONFIG, ResolutionBand
from cipher.schemas.graph.ontology import EntityType

CFG = DEFAULT_RESOLUTION_CONFIG


def _group(**kw):
    g = {
        "entity_type": EntityType.PERSON,
        "normalized_value": "nick bolton",
        "mention_ids": ["m1", "m2", "m3"],
        "surface_texts": ["Nick Bolton", "Nick Bolton", "nick bolton"],
        "from_structured": False,
    }
    g.update(kw)
    return g


def _sc(score, band, *, vetoed=False, eid="e1"):
    return ScoredCandidate(
        entity_id=eid,
        score=score,
        vetoed=vetoed,
        features=[],
        match_method=EntityMatchMethod.SELECTOR_BLOCKING,
        blocked_by=("selector",),
        band=band,
    )


def test_pick_display_name_is_the_mode():
    """Most common surface form wins, original casing kept."""
    assert _pick_display_name(["Nick Bolton", "nick bolton", "Nick Bolton"]) == "Nick Bolton"


def test_provenance_reflects_structured_flag():
    """A group with a structured-field mention scores off the email-header prior."""
    assert _provenance_for_group(_group(from_structured=True)) == "email_header"
    assert _provenance_for_group(_group(from_structured=False)) == "text"


def test_scoring_input_carries_group_fields():
    """The scorer input is built straight off the group + precomputed context."""
    mi = _mention_scoring_input(_group(from_structured=True), name_df=5, selector_values=frozenset({"a@b.com"}))
    assert mi.name == "Nick Bolton"
    assert mi.normalized_name == "nick bolton"
    assert mi.entity_type is EntityType.PERSON
    assert mi.provenance == "email_header"
    assert mi.selector_values == frozenset({"a@b.com"})
    assert mi.name_df == 5


def test_plan_auto_when_top_band_auto():
    """A top AUTO candidate -> the sweep attaches the group now."""
    assert _plan(_group(), [_sc(0.95, ResolutionBand.AUTO)], CFG) == "auto"


def test_plan_review_when_any_review_band():
    """No auto, but a review-worthy candidate -> file it for the queue."""
    assert _plan(_group(), [_sc(0.7, ResolutionBand.REVIEW)], CFG) == "review"


def test_plan_provisional_for_trustworthy_typed_group():
    """Nothing surfaced, but a typed group with enough mentions -> provisional entity."""
    assert _plan(_group(mention_ids=["m1", "m2", "m3"]), [_sc(0.2, None)], CFG) == "provisional"


def test_plan_left_for_untyped_group_with_no_candidate():
    """An untyped email-header name with no match is left for an analyst."""
    g = _group(entity_type=None, from_structured=True, mention_ids=["m1"])
    assert _plan(g, [], CFG) == "left"


def test_plan_left_when_thin_and_no_candidate():
    """A one-off prose name with no candidate and below the min-mentions floor is left."""
    assert _plan(_group(mention_ids=["m1"], from_structured=False), [], CFG) == "left"


def test_plan_ignores_vetoed_candidates():
    """A vetoed top candidate never drives an auto/review plan."""
    g = _group(mention_ids=["m1"], from_structured=False)
    assert _plan(g, [_sc(0.99, ResolutionBand.AUTO, vetoed=True)], CFG) == "left"


def test_plan_respects_no_create():
    """--no-create (create_provisional=False) turns a would-be provisional into left."""
    cfg = CFG.model_copy(update={"create_provisional": False})
    assert _plan(_group(), [_sc(0.2, None)], cfg) == "left"
