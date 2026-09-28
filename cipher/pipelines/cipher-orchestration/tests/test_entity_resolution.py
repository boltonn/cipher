"""Pure-logic tests for the Fellegi-Sunter resolution scorer (no DB)."""

from cipher.orchestration.entity_resolution import (
    CandidateScoringInput,
    MentionScoringInput,
    build_explanation,
    decide,
    score_candidate,
)
from cipher.schemas.graph.entity_match import EntityMatchMethod
from cipher.schemas.graph.entity_resolution import DEFAULT_RESOLUTION_CONFIG, FeatureLevel, ResolutionBand
from cipher.schemas.graph.ontology import EntityType

CFG = DEFAULT_RESOLUTION_CONFIG


def _mention(name, **kw):
    kw.setdefault("normalized_name", name.lower())
    kw.setdefault("entity_type", EntityType.PERSON)
    kw.setdefault("provenance", "text")
    return MentionScoringInput(name=name, **kw)


def _candidate(name, **kw):
    kw.setdefault("entity_type", EntityType.PERSON)
    kw.setdefault("entity_id", "e1")
    return CandidateScoringInput(display_name=name, **kw)


def test_selector_plus_exact_name_on_header_is_auto():
    """Shared email + exact name from an email header -> AUTO via the selector rule."""
    m = _mention("Nick Bolton", provenance="email_header", selector_values=frozenset({"nbolton@gmail.com"}))
    c = _candidate(
        "Nicholas Bolton", selector_values=frozenset({"nbolton@gmail.com"}), blocked_by=("selector", "name_exact")
    )
    # name_exact needs an exact fold; use the same surface for the exact-name feature.
    c2 = _candidate("Nick Bolton", selector_values=frozenset({"nbolton@gmail.com"}), blocked_by=("selector",))
    sc = score_candidate(m, c2, CFG)
    decide([sc], CFG)
    assert sc.band is ResolutionBand.AUTO
    assert sc.match_method is EntityMatchMethod.SELECTOR_BLOCKING
    assert not sc.vetoed
    # the weaker candidate (name differs) still scores high on the selector alone
    assert score_candidate(m, c, CFG).score > 0.9


def test_exact_name_text_only_is_review_not_auto():
    """An exact name match with no selector is high-scoring but never auto."""
    m = _mention("Jonathan Archer")
    c = _candidate("Jonathan Archer", blocked_by=("name_exact", "key:folded"))
    sc = score_candidate(m, c, CFG)
    decide([sc], CFG)
    assert sc.score > CFG.auto_threshold
    assert sc.band is ResolutionBand.REVIEW  # auto_methods == ['selector'] only


def test_different_surname_and_given_is_vetoed():
    """name_structure CONFLICT zeroes the score regardless of anything else."""
    m = _mention("Nick Bolton")
    c = _candidate("Sarah Whitfield")
    sc = score_candidate(m, c, CFG)
    assert sc.vetoed and sc.score == 0.0
    decide([sc], CFG)
    assert sc.band is None


def test_person_vs_organization_is_vetoed():
    """type_agreement CONFLICT vetoes even a strong name match."""
    m = _mention("Globex", entity_type=EntityType.PERSON)
    c = _candidate("Globex", entity_type=EntityType.ORGANIZATION)
    sc = score_candidate(m, c, CFG)
    assert sc.vetoed


def test_dob_conflict_vetoes_exact_name():
    """A contradicting date of birth beats an exact name."""
    m = _mention("John Smith", attributes={"date_of_birth": "1980-01-01"})
    c = _candidate("John Smith", attributes={"date_of_birth": "1975-06-30"})
    sc = score_candidate(m, c, CFG)
    assert sc.vetoed


def test_same_surname_different_given_is_vetoed():
    """Two fully-spelled, unrelated first names under one surname = a different person."""
    m = _mention("Nick Bolton")
    c = _candidate("Cathi Bolton", trigram_score=0.6)
    sc = score_candidate(m, c, CFG)
    decide([sc], CFG)
    assert sc.vetoed
    assert sc.score == 0.0
    assert sc.band is None
    assert any(f.name == "name_structure" and f.level is FeatureLevel.CONFLICT for f in sc.features)


def test_cross_script_translit_reaches_review():
    """A Cyrillic mention resolving to its romanized entity is at least review-worthy."""
    m = _mention("Иван Петров", culture="east_slavic")
    c = _candidate("Ivan Petrov", blocked_by=("key:translit",))
    sc = score_candidate(m, c, CFG)
    decide([sc], CFG)
    assert sc.band is ResolutionBand.REVIEW
    assert any(f.name == "name_translit" and f.level is FeatureLevel.EXACT for f in sc.features)


def test_term_frequency_downweights_common_names():
    """An exact match on a name shared by many entities scores lower."""
    c = _candidate("John Smith")
    rare = score_candidate(_mention("John Smith", name_df=1), c, CFG).score
    common = score_candidate(_mention("John Smith", name_df=40), c, CFG).score
    assert common < rare


def test_conflicting_name_overrides_shared_mailbox():
    """A shared family mailbox does not rescue a candidate whose first name conflicts."""
    m = _mention("Mary Bolton", provenance="email_header", selector_values=frozenset({"bolton213@yahoo.com"}))
    c = _candidate("Edmond Bolton", selector_values=frozenset({"bolton213@yahoo.com"}), blocked_by=("selector",))
    sc = score_candidate(m, c, CFG)
    decide([sc], CFG)
    assert sc.vetoed
    assert sc.band is None


def test_shared_mailbox_bare_surname_is_review_not_auto():
    """A surname-only mention on a shared address: high score from the selector, but held."""
    m = _mention("Bolton", provenance="email_header", selector_values=frozenset({"bolton213@yahoo.com"}))
    c = _candidate("Edmond Bolton", selector_values=frozenset({"bolton213@yahoo.com"}), blocked_by=("selector",))
    sc = score_candidate(m, c, CFG)
    decide([sc], CFG)
    assert not sc.vetoed
    assert sc.score >= CFG.auto_threshold  # selector alone still scores high
    assert sc.band is ResolutionBand.REVIEW  # but no first name to agree on -> held


def test_shared_mailbox_with_real_name_match_still_autos():
    """Same address + an actual name match -> auto (the family-mailbox guard doesn't over-block)."""
    m = _mention("Cathi Bolton", provenance="email_header", selector_values=frozenset({"bolton213@yahoo.com"}))
    c = _candidate("Cathi Bolton", selector_values=frozenset({"bolton213@yahoo.com"}), blocked_by=("selector",))
    sc = score_candidate(m, c, CFG)
    decide([sc], CFG)
    assert sc.band is ResolutionBand.AUTO


def test_name_agreement_guard_can_be_disabled():
    """`require_name_agreement_for_auto=False` restores selector-only auto (no name conflict)."""
    cfg = CFG.model_copy(update={"require_name_agreement_for_auto": False})
    m = _mention("Bolton", provenance="email_header", selector_values=frozenset({"x@y.com"}))
    c = _candidate("Edmond Bolton", selector_values=frozenset({"x@y.com"}), blocked_by=("selector",))
    sc = score_candidate(m, c, cfg)
    decide([sc], cfg)
    assert sc.band is ResolutionBand.AUTO


def test_given_name_initial_surname_ranks_above_conflict():
    """'Nick Bolton' vs 'Nick B' (given exact, surname initial) beats 'Edmond Bolton' (vetoed)."""
    m = _mention("Nick Bolton", provenance="email_header", selector_values=frozenset({"bolton213@yahoo.com"}))
    right = _candidate(
        "Nick B", entity_id="nick-b", selector_values=frozenset({"bolton213@yahoo.com"}), blocked_by=("selector",)
    )
    wrong = _candidate(
        "Edmond Bolton", entity_id="ed", selector_values=frozenset({"bolton213@yahoo.com"}), blocked_by=("selector",)
    )
    scored = [score_candidate(m, right, CFG), score_candidate(m, wrong, CFG)]
    decide(scored, CFG)
    by_id = {s.entity_id: s for s in scored}
    assert not by_id["nick-b"].vetoed
    assert by_id["ed"].vetoed
    assert by_id["nick-b"].score > by_id["ed"].score


def test_decide_margin_blocks_ambiguous_auto():
    """Two near-tied top candidates: neither auto-resolves."""
    m = _mention("A B", provenance="email_header", selector_values=frozenset({"x@y.com"}))
    c1 = _candidate("A B", entity_id="e1", selector_values=frozenset({"x@y.com"}), blocked_by=("selector",))
    c2 = _candidate("A B", entity_id="e2", selector_values=frozenset({"x@y.com"}), blocked_by=("selector",))
    scored = [score_candidate(m, c1, CFG), score_candidate(m, c2, CFG)]
    decide(scored, CFG)
    assert all(s.band is not ResolutionBand.AUTO for s in scored)


def test_build_explanation_shape():
    """The stored explanation carries the non-empty features and the band."""
    m = _mention("Nick Bolton", provenance="email_header", selector_values=frozenset({"nb@x.com"}))
    c = _candidate("Nick Bolton", selector_values=frozenset({"nb@x.com"}), blocked_by=("selector",))
    sc = score_candidate(m, c, CFG)
    decide([sc], CFG)
    exp = build_explanation(sc, candidates_considered=1, runner_up_score=None, config=CFG)
    assert exp.band is sc.band
    assert exp.blocking == ["selector"]
    assert all(f.level is not FeatureLevel.NONE for f in exp.features)
    assert any(f.name == "selector_overlap" for f in exp.features)
