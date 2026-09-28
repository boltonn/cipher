"""Pure-logic tests for batch face-match proposal de-duplication (no DB)."""

from cipher.orchestration.match_faces import _dedupe_matches
from cipher.schemas.identity.face_match import FaceMatchMethod


def test_dedupe_keeps_best_score_per_face_person_pair():
    # same (face, person) proposed twice (two representative faces of one person)
    out = _dedupe_matches([("f1", "p1", 0.72), ("f1", "p1", 0.81), ("f2", "p1", 0.65)])
    by_pair = {(m.face_id, m.person_id): m.similarity_score for m in out}
    assert by_pair == {("f1", "p1"): 0.81, ("f2", "p1"): 0.65}
    assert all(m.match_method == FaceMatchMethod.AUTOMATIC_SIMILARITY for m in out)


def test_dedupe_keeps_distinct_people_for_one_face():
    out = _dedupe_matches([("f1", "p1", 0.7), ("f1", "p2", 0.68)])
    assert {(m.face_id, m.person_id) for m in out} == {("f1", "p1"), ("f1", "p2")}


def test_dedupe_empty():
    assert _dedupe_matches([]) == []
